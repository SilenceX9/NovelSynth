from fastapi import APIRouter, HTTPException, Query

from app.models.context import IndexResponse
from app.modules.indexer.chapter_parser import parse_chapters
from app.modules.indexer.service import (
    start_or_resume_index, pause_index, resume_index,
)
from app.task_manager import (
    get_task_manager, init_task_manager, TASK_INDEX,
    STATUS_RUNNING, STATUS_PAUSED, STATUS_DONE, STATUS_PENDING, STATUS_FAILED,
)
from app.storage import Storage

router = APIRouter(prefix="/api/index", tags=["index"])
storage = Storage()


async def _get_chapters(book_id: str) -> tuple[list[dict], str]:
    """Get chapters for a book. Prefer chapters.json (EPUB) over parsing original.txt (TXT)."""
    chapters = await storage.load_chapters(book_id)
    if chapters is not None:
        # EPUB book: filter noise chapters
        clean = [c for c in chapters if not c.get("is_noise")]
    else:
        # TXT book: parse from original
        original = await storage.load_original(book_id)
        if not original:
            raise HTTPException(404, "Book not found")
        clean = parse_chapters(original)
    books = await storage.list_books()
    book_title = next((b["title"] for b in books if b["book_id"] == book_id), f"book_{book_id}")
    return clean, book_title


@router.post("/{book_id}/start")
async def start_index(
    book_id: str,
    start_chapter: int = Query(default=1, ge=1, description="Start chapter (1-based)"),
    end_chapter: int = Query(default=-1, description="End chapter (-1 = all)"),
):
    """启动或恢复索引任务。支持指定章节范围。"""
    chapters, book_title = await _get_chapters(book_id)

    # Apply chapter range
    if end_chapter == -1 or end_chapter > len(chapters):
        end_chapter = len(chapters)
    if start_chapter > end_chapter:
        start_chapter = end_chapter
    selected = chapters[start_chapter - 1 : end_chapter]

    # Re-number selected chapters to 1..N
    for i, ch in enumerate(selected):
        ch["number"] = i + 1

    # Combine chapter texts for processing
    combined = "\n\n".join(f"{ch['title']}\n{ch['text']}" for ch in selected)

    task = await start_or_resume_index(book_id, combined, selected, book_title)
    return task.to_dict()


@router.get("/{book_id}/status")
async def get_index_status(book_id: str):
    """查询索引进度。"""
    tm = get_task_manager(storage)
    task = await tm.load(book_id, TASK_INDEX)
    if task is None:
        status = await storage.get_status(book_id)
        if status.get("indexed"):
            return {"step": "完成", "current": 0, "total": 0, "tokens": 0, "elapsed": 0, "status": "done"}
        return {"step": "not_started", "current": 0, "total": 0, "tokens": 0, "elapsed": 0, "status": "not_started"}
    return task.to_dict()


@router.post("/{book_id}/pause")
async def pause_index_task(book_id: str):
    """暂停索引任务。"""
    task = await pause_index(book_id)
    if task is None:
        raise HTTPException(404, "No running index task")
    return task.to_dict()


@router.post("/{book_id}/resume")
async def resume_index_task(book_id: str):
    """恢复索引任务。"""
    chapters, book_title = await _get_chapters(book_id)
    combined = "\n\n".join(f"{ch['title']}\n{ch['text']}" for ch in chapters)
    task = await resume_index(book_id, combined, chapters, book_title)
    if task is None:
        raise HTTPException(404, "No paused index task")
    return task.to_dict()


@router.post("/{book_id}")
async def trigger_index(book_id: str):
    """兼容旧接口：启动索引并阻塞等待完成（不推荐）"""
    chapters, book_title = await _get_chapters(book_id)
    combined = "\n\n".join(f"{ch['title']}\n{ch['text']}" for ch in chapters)

    from app.modules.indexer.service import _run_index_task, _run_index_task_wrapper
    from app.task_manager import TaskState, STATUS_RUNNING

    task = TaskState(book_id=book_id, task_type=TASK_INDEX, total=len(chapters))
    ctx = await _run_index_task(task, combined, chapters, book_title)

    if ctx is not None:
        await storage.save_context(book_id, ctx)
        await storage.mark_indexed(book_id)

    from app.llm_client import LLMClient
    metrics = LLMClient.get_metrics()
    return IndexResponse(
        book_id=book_id, context=ctx, status="completed",
        tokens=metrics["total_tokens"],
        elapsed=metrics.get("elapsed", 0),
    )


@router.get("/{book_id}/context")
async def get_context(book_id: str):
    ctx = await storage.load_context(book_id)
    if ctx is None:
        raise HTTPException(404, "Context not found")
    return ctx
