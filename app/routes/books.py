from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.storage import Storage
from app.task_manager import get_task_manager, TASK_INDEX, TASK_DEHYDRATE

router = APIRouter(prefix="/api/books", tags=["books"])
storage = Storage()


class UploadResponse(BaseModel):
    book_id: str
    new_chapters: int = 0


class BookInfo(BaseModel):
    book_id: str
    title: str
    indexed: bool
    dehydrated: bool


@router.post("/upload", response_model=UploadResponse)
async def upload_book(file: UploadFile = File(...)):
    content = await file.read()
    text = content.decode("utf-8")
    title = file.filename or "unknown"
    book_id = await storage.create_book(title, text)

    from app.modules.indexer.chapter_parser import parse_chapters
    chapters = parse_chapters(text)
    return UploadResponse(book_id=book_id, new_chapters=len(chapters))


@router.get("/", response_model=list[BookInfo])
async def list_books():
    return await storage.list_books()


@router.get("/with-tasks")
async def list_books_with_tasks():
    """返回书籍列表 + 每本书的任务状态详情。"""
    books = await storage.list_books()
    tm = get_task_manager(storage)
    result = []
    for b in books:
        book_id = b["book_id"]
        index_task = await tm.load(book_id, TASK_INDEX)
        dehydrate_task = await tm.load(book_id, TASK_DEHYDRATE)
        result.append({
            **b,
            "index_status": index_task.status if index_task else ("done" if b["indexed"] else None),
            "index_step": index_task.step if index_task else "",
            "dehydrate_status": dehydrate_task.status if dehydrate_task else ("done" if b["dehydrated"] else None),
            "dehydrate_step": dehydrate_task.step if dehydrate_task else "",
        })
    return result


@router.post("/{book_id}/append", response_model=UploadResponse)
async def append_to_book(book_id: str, file: UploadFile = File(...)):
    """追加新文本到现有书籍。只处理新增章节，不重置已有索引/脱水结果。"""
    existing = await storage.load_original(book_id)
    if not existing:
        raise HTTPException(404, "Book not found")

    content = await file.read()
    new_text = content.decode("utf-8")

    # Parse existing chapters to get dedup keys
    from app.modules.indexer.chapter_parser import parse_chapters
    existing_chapters = parse_chapters(existing)
    existing_titles = set(ch["title"] for ch in existing_chapters)

    # Parse new chapters and dedup
    new_chapters = parse_chapters(new_text)
    added_chapters = [ch for ch in new_chapters if ch["title"] not in existing_titles]

    if not added_chapters:
        # All chapters already exist
        return {"book_id": book_id, "new_chapters": 0}

    # Append only new chapter content
    new_texts = []
    for ch in added_chapters:
        new_texts.append(f"{ch['title']}\n{ch['text']}")

    combined = existing + "\n\n" + "\n\n".join(new_texts)
    await storage.save_original(book_id, combined)

    # Do NOT reset indexed/dehydrated — incremental update
    return {"book_id": book_id, "new_chapters": len(added_chapters)}


@router.get("/{book_id}/status")
async def get_status(book_id: str):
    return await storage.get_status(book_id)


@router.delete("/{book_id}")
async def delete_book(book_id: str):
    await storage.delete_book(book_id)
    return {"status": "ok"}
