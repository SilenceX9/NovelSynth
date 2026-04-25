from fastapi import APIRouter, HTTPException

from app.models.context import IndexResponse
from app.modules.indexer.service import index_novel
from app.storage import Storage

router = APIRouter(prefix="/api/index", tags=["index"])
storage = Storage()


@router.post("/{book_id}", response_model=IndexResponse)
async def trigger_index(book_id: str):
    original = await storage.load_original(book_id)
    if not original:
        raise HTTPException(404, "Book not found")

    try:
        ctx = await index_novel(book_id, original, book_id)
        await storage.save_context(book_id, ctx)
        await storage.mark_indexed(book_id)
        return IndexResponse(book_id=book_id, context=ctx, status="completed")
    except Exception as e:
        return IndexResponse(book_id=book_id, status="failed", error=str(e))


@router.get("/{book_id}/context")
async def get_context(book_id: str):
    ctx = await storage.load_context(book_id)
    if ctx is None:
        raise HTTPException(404, "Context not found")
    return ctx
