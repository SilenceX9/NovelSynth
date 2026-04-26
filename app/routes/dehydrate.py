from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from urllib.parse import quote

from app.modules.dehydration.service import (
    start_or_resume_dehydrate, pause_dehydrate, resume_dehydrate,
)
from app.task_manager import (
    get_task_manager, init_task_manager, TASK_DEHYDRATE,
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


@router.post("/{book_id}/start")
async def start_dehydrate(book_id: str):
    """启动或恢复脱水任务。"""
    ctx = await storage.load_context(book_id)
    if ctx is None:
        raise HTTPException(404, "Context not found. Please index the book first.")

    original = await storage.load_original(book_id)
    if not original:
        raise HTTPException(404, "Book not found")

    from app.modules.indexer.chapter_parser import parse_chapters
    chapters = parse_chapters(original)

    task = await start_or_resume_dehydrate(book_id, ctx, chapters)
    return task.to_dict()


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
    ctx = await storage.load_context(book_id)
    if ctx is None:
        raise HTTPException(404, "Context not found")

    original = await storage.load_original(book_id)
    if not original:
        raise HTTPException(404, "Book not found")

    from app.modules.indexer.chapter_parser import parse_chapters
    chapters = parse_chapters(original)

    task = await resume_dehydrate(book_id, ctx, chapters)
    if task is None:
        raise HTTPException(404, "No paused dehydrate task")
    return task.to_dict()


@router.post("/{book_id}")
async def trigger_dehydrate(book_id: str):
    """兼容旧接口：启动脱水（后台异步）。"""
    ctx = await storage.load_context(book_id)
    if ctx is None:
        raise HTTPException(404, "Context not found. Please index the book first.")

    original = await storage.load_original(book_id)
    if not original:
        raise HTTPException(404, "Book not found")

    from app.modules.indexer.chapter_parser import parse_chapters
    chapters = parse_chapters(original)

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
    return {"blocks": blocks}


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
    # Fallback: parse from original text
    original = await storage.load_original(book_id)
    if not original:
        raise HTTPException(404, "Book not found")
    from app.modules.indexer.chapter_parser import parse_chapters
    parsed = parse_chapters(original)
    return {"chapters": [{"index": i, "title": ch["title"]} for i, ch in enumerate(parsed)]}


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
