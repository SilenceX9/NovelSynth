from fastapi import APIRouter

from app.task_manager import get_task_manager, TASK_INDEX, TASK_DEHYDRATE
from app.storage import Storage

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
storage = Storage()


@router.get("/")
async def list_tasks():
    """返回所有活跃任务。"""
    tm = get_task_manager(storage)
    return await tm.list_active()


@router.get("/book/{book_id}")
async def get_book_tasks(book_id: str):
    """返回某本书的所有任务状态。"""
    tm = get_task_manager(storage)
    index_task = await tm.load(book_id, TASK_INDEX)
    dehydrate_task = await tm.load(book_id, TASK_DEHYDRATE)

    # Load history for both tasks
    index_history = await tm.list_history(book_id, TASK_INDEX)
    dehydrate_history = await tm.list_history(book_id, TASK_DEHYDRATE)

    status = await storage.get_status(book_id)
    books = await storage.list_books()
    book_title = next((b["title"] for b in books if b["book_id"] == book_id), book_id)

    # Count chapters
    try:
        original = await storage.load_original(book_id)
        from app.modules.indexer.chapter_parser import parse_chapters
        chapters = parse_chapters(original)
        total_chapters = len(chapters)
    except Exception:
        total_chapters = 0

    return {
        "book_id": book_id,
        "title": book_title,
        "total_chapters": total_chapters,
        "indexed": status.get("indexed", False),
        "dehydrated": status.get("dehydrated", False),
        "index": index_task.to_dict() if index_task else None,
        "dehydrate": dehydrate_task.to_dict() if dehydrate_task else None,
        "index_history": index_history,
        "dehydrate_history": dehydrate_history,
    }
