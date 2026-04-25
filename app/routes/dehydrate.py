from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.modules.dehydration.service import dehydrate_chapter, assemble_dehydrated
from app.storage import Storage

router = APIRouter(prefix="/api/dehydrate", tags=["dehydrate"])
storage = Storage()


class DehydrateProgress(BaseModel):
    chapter: int
    total: int
    status: str


@router.post("/{book_id}")
async def trigger_dehydrate(book_id: str):
    ctx = await storage.load_context(book_id)
    if ctx is None:
        raise HTTPException(404, "Context not found. Please index the book first.")

    original = await storage.load_original(book_id)
    if not original:
        raise HTTPException(404, "Book not found")

    from app.modules.indexer.chapter_parser import parse_chapters
    chapters = parse_chapters(original)

    dehydrated_parts = []
    for i, ch in enumerate(chapters):
        blocks = await dehydrate_chapter(ch["text"], ctx)
        dehydrated_text = assemble_dehydrated(blocks)
        dehydrated_parts.append(dehydrated_text)

    full_dehydrated = "\n\n".join(dehydrated_parts)
    await storage.save_dehydrated(book_id, full_dehydrated)
    await storage.mark_dehydrated(book_id)
    return {"status": "completed", "total_chapters": len(chapters)}


@router.get("/{book_id}/progress", response_model=DehydrateProgress)
async def get_progress(book_id: str):
    """MVP 简化：只返回 completed/not_started。完整 SSE 进度后续迭代加。"""
    status = await storage.get_status(book_id)
    if status.get("dehydrated"):
        return DehydrateProgress(chapter=0, total=0, status="completed")
    return DehydrateProgress(chapter=0, total=0, status="not_started")


@router.get("/{book_id}/output")
async def get_output(book_id: str):
    text = await storage.load_dehydrated(book_id)
    if not text:
        raise HTTPException(404, "Dehydrated output not found")
    return {"text": text}
