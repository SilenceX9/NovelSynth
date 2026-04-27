from fastapi import APIRouter
from pathlib import Path

from app.task_manager import get_task_manager, TASK_INDEX, TASK_DEHYDRATE
from app.storage import Storage

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
storage = Storage()


def _load_failed_chapters(book_id: str) -> list[dict]:
    """Load failed chapter info from checkpoint."""
    p = Path("data") / book_id / "dehydrate_checkpoint.json"
    if not p.exists():
        return []
    try:
        import json
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("failed", [])
    except Exception:
        return []


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

    # Load failed chapter info
    failed_chapters = _load_failed_chapters(book_id)

    # Count dehydrated chapters (from saved results)
    dehydrated_chapters = await storage.load_chapter_dehydrated(book_id)
    dehydrated_count = len([ch for ch in dehydrated_chapters if ch.get("text")])

    return {
        "book_id": book_id,
        "title": book_title,
        "total_chapters": total_chapters,
        "dehydrated_count": dehydrated_count,
        "indexed": status.get("indexed", False),
        "dehydrated": status.get("dehydrated", False),
        "index": index_task.to_dict() if index_task else None,
        "dehydrate": _enrich_dehydrate_task(dehydrate_task, book_id),
        "index_history": index_history,
        "dehydrate_history": dehydrate_history,
        "failed_chapters": failed_chapters,
    }


def _enrich_dehydrate_task(task: "TaskState | None", book_id: str) -> dict | None:
    """Add checkpoint-completed chapters to dehydrate task response."""
    if task is None:
        return None
    result = task.to_dict()
    # For dehydrate tasks, load completed chapters from checkpoint
    # (task.completed may be stale since checkpoints are the source of truth)
    from pathlib import Path
    import json
    p = Path("data") / book_id / "dehydrate_checkpoint.json"
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            result["completed"] = sorted(data.get("completed", []))
        except Exception:
            pass
    return result
