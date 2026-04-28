from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from urllib.parse import quote

from app.modules.dehydration.service import (
    start_or_resume_dehydrate, pause_dehydrate, resume_dehydrate,
    retry_failed_chapters,
)
from app.modules.indexer.chapter_parser import parse_chapters
from app.modules.indexer.service import start_or_resume_index as _start_index
from app.models.context import GlobalContext
from app.task_manager import (
    get_task_manager, init_task_manager, TASK_DEHYDRATE, TASK_INDEX,
    STATUS_RUNNING, STATUS_PAUSED, STATUS_DONE, STATUS_PENDING, STATUS_FAILED,
)
from app.utils.epub_builder import build_epub
from app.storage import Storage

router = APIRouter(prefix="/api/dehydrate", tags=["dehydrate"])
storage = Storage()


class DehydrateProgress(BaseModel):
    chapter: int
    total: int
    status: str
    tokens: int = 0
    elapsed: float = 0.0


async def _get_chapters(book_id: str) -> tuple[list[dict], GlobalContext]:
    """Get chapters for a book. Prefer chapters.json (EPUB) over parsing original.txt (TXT)."""
    ctx = await storage.load_context(book_id)
    if ctx is None:
        raise HTTPException(404, "Context not found. Please index the book first.")

    chapters = await storage.load_chapters(book_id)
    if chapters is None:
        from app.modules.indexer.chapter_parser import parse_chapters
        original = await storage.load_original(book_id)
        if not original:
            raise HTTPException(404, "Book not found")
        chapters = parse_chapters(original)
    # Always filter out noise chapters so dehydration indices align with saved results
    clean = [c for c in chapters if not c.get("is_noise")]
    # Re-index sequentially
    for i, ch in enumerate(clean):
        ch["number"] = i + 1
    return clean, ctx


@router.post("/{book_id}/start")
async def start_dehydrate(
    book_id: str,
    start_chapter: int = Query(default=1, ge=1),
    end_chapter: int = Query(default=-1),
):
    """启动或恢复脱水任务。支持指定章节范围。"""
    chapters, ctx = await _get_chapters(book_id)
    # chapters are already clean and sequentially numbered from _get_chapters

    if end_chapter == -1 or end_chapter > len(chapters):
        end_chapter = len(chapters)
    if start_chapter > end_chapter:
        start_chapter = end_chapter
    selected = chapters[start_chapter - 1 : end_chapter]

    task = await start_or_resume_dehydrate(book_id, ctx, selected)
    return task.to_dict()


@router.post("/{book_id}/restart")
async def restart_dehydrate(
    book_id: str,
    start_chapter: int = Query(default=1, ge=1),
    end_chapter: int = Query(default=-1),
):
    """重新开始脱水任务（清除已完成状态和检查点）。用于失败任务一键重试。"""
    tm = get_task_manager(storage)
    existing = await tm.load(book_id, TASK_DEHYDRATE)

    # Clear existing task and checkpoint
    if existing:
        await tm.delete(book_id, TASK_DEHYDRATE)
        from pathlib import Path
        p = Path("data") / book_id / "dehydrate_checkpoint.json"
        if p.exists():
            p.unlink()
        # Also clear saved dehydrate results
        await storage.save_dehydrated(book_id, "")
        await storage.save_dehydrated_blocks(book_id, [])
        await storage.save_chapter_dehydrated(book_id, [])

    # Start fresh
    chapters, ctx = await _get_chapters(book_id)
    if end_chapter == -1 or end_chapter > len(chapters):
        end_chapter = len(chapters)
    if start_chapter > end_chapter:
        start_chapter = end_chapter
    selected = chapters[start_chapter - 1 : end_chapter]

    task = await start_or_resume_dehydrate(book_id, ctx, selected)
    return task.to_dict()


@router.post("/{book_id}/index-and-dehydrate")
async def index_and_dehydrate(
    book_id: str,
    start_chapter: int = Query(default=1, ge=1),
    end_chapter: int = Query(default=-1),
):
    """一键操作：先索引再脱水。索引完成后自动开始脱水。"""
    # Load chapters directly (without requiring context)
    chapters = await storage.load_chapters(book_id)
    if chapters is None:
        from app.modules.indexer.chapter_parser import parse_chapters
        original = await storage.load_original(book_id)
        if not original:
            raise HTTPException(404, "Book not found")
        chapters = parse_chapters(original)
    clean = [c for c in chapters if not c.get("is_noise")]
    for i, ch in enumerate(clean):
        ch["number"] = i + 1

    if end_chapter == -1 or end_chapter > len(clean):
        end_chapter = len(clean)
    if start_chapter > end_chapter:
        start_chapter = end_chapter
    selected = clean[start_chapter - 1 : end_chapter]

    # Combine chapter texts
    combined = "\n\n".join(f"{ch['title']}\n{ch['text']}" for ch in selected)

    tm = get_task_manager(storage)

    # Clean up any existing dehydrate state to avoid stale task data
    existing_dh = await tm.load(book_id, TASK_DEHYDRATE)
    if existing_dh:
        await tm.delete(book_id, TASK_DEHYDRATE)
        from pathlib import Path
        p = Path("data") / book_id / "dehydrate_checkpoint.json"
        if p.exists():
            p.unlink()

    # Check if index already done
    index_task = await tm.load(book_id, TASK_INDEX)
    if index_task and index_task.status == STATUS_DONE:
        ctx = await storage.load_context(book_id)
        if ctx:
            task = await start_or_resume_dehydrate(book_id, ctx, selected)
            return {"index": "already_done", "dehydrate": task.to_dict()}

    # Clear previous index task if it existed
    if index_task and index_task.status in (STATUS_DONE, STATUS_FAILED):
        await tm.delete(book_id, TASK_INDEX)

    book_title = ""
    try:
        books = await storage.list_books()
        for b in books:
            if b["book_id"] == book_id:
                book_title = b["title"]
                break
    except Exception:
        pass

    index_task = await _start_index(book_id, combined, selected, book_title)

    # Create a wrapper that starts dehydrate after index completes
    async def _run_dehydrate_after_index():
        try:
            import asyncio
            for _ in range(600):  # max 10 minutes
                await asyncio.sleep(1)
                current = await tm.load(book_id, TASK_INDEX)
                if not current or current.status == STATUS_DONE:
                    break
                if current.status == STATUS_FAILED:
                    return

            ctx = await storage.load_context(book_id)
            if ctx:
                await storage.mark_indexed(book_id)
                await start_or_resume_dehydrate(book_id, ctx, selected)
        except Exception as e:
            logger = __import__('logging').getLogger(__name__)
            logger.exception(f"index-and-dehydrate: failed to start dehydrate after index")

    import asyncio
    asyncio.create_task(_run_dehydrate_after_index())

    return {"index": index_task.to_dict(), "dehydrate": "queued_after_index"}


@router.get("/{book_id}/status")
async def get_dehydrate_status(book_id: str):
    """查询脱水进度。"""
    tm = get_task_manager(storage)
    task = await tm.load(book_id, TASK_DEHYDRATE)
    if task is None:
        status = await storage.get_status(book_id)
        if status.get("dehydrated"):
            return {"step": "完成", "current": 0, "total": 0, "tokens": 0, "elapsed": 0, "status": "done"}
        return {"step": "not_started", "current": 0, "total": 0, "tokens": 0, "elapsed": 0, "status": "not_started"}
    return task.to_dict()


@router.post("/{book_id}/pause")
async def pause_dehydrate_task(book_id: str):
    """暂停脱水任务。"""
    task = await pause_dehydrate(book_id)
    if task is None:
        raise HTTPException(404, "No running dehydrate task")
    return task.to_dict()


@router.post("/{book_id}/resume")
async def resume_dehydrate_task(book_id: str):
    """恢复脱水任务。"""
    chapters, ctx = await _get_chapters(book_id)
    task = await resume_dehydrate(book_id, ctx, chapters)
    if task is None:
        raise HTTPException(404, "No paused dehydrate task")
    return task.to_dict()


@router.get("/{book_id}/failed-chapters")
async def get_failed_chapters(book_id: str):
    """返回失败章节列表及失败原因。"""
    from pathlib import Path
    p = Path("data") / book_id / "dehydrate_checkpoint.json"
    if not p.exists():
        return {"failed": []}
    try:
        import json
        data = json.loads(p.read_text(encoding="utf-8"))
        failed = data.get("failed", [])
        return {"failed": failed}
    except Exception:
        return {"failed": []}


@router.post("/{book_id}/retry-failed")
async def retry_failed(book_id: str):
    """重试失败的脱水章节。"""
    chapters, ctx = await _get_chapters(book_id)
    task = await retry_failed_chapters(book_id, ctx, chapters)
    if task is None:
        raise HTTPException(404, "No failed chapters to retry")
    return task.to_dict()


@router.post("/{book_id}")
async def trigger_dehydrate(book_id: str):
    """兼容旧接口：启动脱水（后台异步）。"""
    chapters, ctx = await _get_chapters(book_id)
    task = await start_or_resume_dehydrate(book_id, ctx, chapters)
    return {
        "status": "started",
        "total_chapters": len(chapters),
        "task_id": book_id,
    }


@router.get("/{book_id}/progress", response_model=DehydrateProgress)
async def get_progress(book_id: str):
    """查询脱水进度。兼容旧接口。"""
    tm = get_task_manager(storage)
    task = await tm.load(book_id, TASK_DEHYDRATE)
    if task is None:
        status = await storage.get_status(book_id)
        if status.get("dehydrated"):
            return DehydrateProgress(chapter=0, total=0, status="completed")
        return DehydrateProgress(chapter=0, total=0, status="not_started")
    return DehydrateProgress(
        chapter=task.current,
        total=task.total,
        status=task.step if task.status == STATUS_RUNNING else task.status,
        tokens=task.tokens,
        elapsed=task.elapsed,
    )


@router.get("/{book_id}/output")
async def get_output(book_id: str):
    text = await storage.load_dehydrated(book_id)
    if not text:
        raise HTTPException(404, "Dehydrated output not found")
    return {"text": text}


@router.get("/{book_id}/structured")
async def get_structured(book_id: str):
    blocks = await storage.load_dehydrated_blocks(book_id)
    if not blocks:
        raise HTTPException(404, "Structured output not found")
    stats = await storage.load_dehydrate_stats(book_id)
    return {"blocks": blocks, "stats": stats}


@router.get("/{book_id}/export/txt", response_class=PlainTextResponse)
async def export_txt(book_id: str):
    text = await storage.load_dehydrated(book_id)
    if not text:
        raise HTTPException(404, "Dehydrated text not found")
    headers = {
        "Content-Disposition": f'attachment; filename="dehydrated.txt"',
        "Content-Type": "text/plain; charset=utf-8",
    }
    return PlainTextResponse(content=text, headers=headers)


@router.get("/{book_id}/chapters")
async def get_chapter_list(book_id: str):
    """返回章节标题列表，用于阅读器目录导航。"""
    chapters = await storage.load_chapter_dehydrated(book_id)
    if chapters:
        return {"chapters": [{"index": i, "title": ch["title"]} for i, ch in enumerate(chapters)]}
    # Fallback: prefer chapters.json (EPUB), then parse original (TXT)
    chapters = await storage.load_chapters(book_id)
    if chapters:
        clean = [c for c in chapters if not c.get("is_noise")]
        return {"chapters": [{"index": i, "title": ch["title"]} for i, ch in enumerate(clean)]}
    original = await storage.load_original(book_id)
    if not original:
        raise HTTPException(404, "Book not found")
    from app.modules.indexer.chapter_parser import parse_chapters
    parsed = parse_chapters(original)
    return {"chapters": [{"index": i, "title": ch["title"]} for i, ch in enumerate(parsed)]}


@router.get("/{book_id}/chapter/{chapter_idx}")
async def get_single_chapter(book_id: str, chapter_idx: int):
    """读取单章脱水内容。后台脱水仍在进行时也可读取已完成的章节。"""
    chapters = await storage.load_chapter_dehydrated(book_id)
    if not chapters or chapter_idx >= len(chapters) or not chapters[chapter_idx].get("text"):
        # Chapter not yet dehydrated — try to return original text as fallback
        original_chapters = await storage.load_chapters(book_id)
        if original_chapters and chapter_idx < len(original_chapters):
            ch = original_chapters[chapter_idx]
            return {"title": ch["title"], "text": ch["text"], "status": "pending"}
        raise HTTPException(404, f"Chapter {chapter_idx} not found")
    ch = chapters[chapter_idx]
    # Also return task progress context
    tm = get_task_manager(storage)
    task = await tm.load(book_id, TASK_DEHYDRATE)
    progress = {"current": task.current if task else 0, "total": task.total if task else 0}
    return {"title": ch["title"], "text": ch["text"], "status": "done", "progress": progress}


@router.get("/{book_id}/export/epub")
async def export_epub(book_id: str):
    chapters = await storage.load_chapter_dehydrated(book_id)
    if not chapters:
        text = await storage.load_dehydrated(book_id)
        if not text:
            raise HTTPException(404, "No dehydrated content found")
        chapters = [{"title": "正文", "text": text}]

    title = "未命名小说"
    try:
        books = await storage.list_books()
        for b in books:
            if b["book_id"] == book_id:
                title = b["title"]
                break
    except Exception:
        pass

    epub_bytes = build_epub(
        title=title,
        author="AI 脱水版",
        chapters=[(ch["title"], ch["text"]) for ch in chapters],
    )

    safe_title = title.replace('"', '_').replace(';', '_')
    ascii_name = safe_title.encode('ascii', 'ignore').decode('ascii').replace(' ', '_') or 'dehydrated'
    headers = {
        "Content-Disposition": f'attachment; filename="{ascii_name}.epub"; filename*=UTF-8\'\'{quote(safe_title + ".epub")}',
        "Content-Type": "application/epub+zip",
    }
    return Response(content=epub_bytes, media_type="application/epub+zip", headers=headers)
