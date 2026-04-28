from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from app.storage import Storage
from app.task_manager import get_task_manager, TASK_INDEX, TASK_DEHYDRATE

router = APIRouter(prefix="/api/books", tags=["books"])
storage = Storage()


class UploadResponse(BaseModel):
    book_id: str
    new_chapters: int = 0
    format: str = "txt"  # "txt" or "epub"


class BookInfo(BaseModel):
    book_id: str
    title: str
    indexed: bool
    dehydrated: bool
    total_chapters: int = 0


class ChapterPreview(BaseModel):
    book_id: str
    total_chapters: int
    chapters: list[dict]  # {"number": int, "title": str, "char_count": int}


@router.post("/preview-epub")
async def preview_epub(file: UploadFile = File(...)):
    """Preview EPUB chapter stats without saving. Returns chapter count, noise list, etc."""
    import tempfile
    import os
    from app.modules.indexer.epub_parser import parse_epub, count_chapters

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        info = count_chapters(tmp_path)
        chapters = parse_epub(tmp_path)
    finally:
        os.unlink(tmp_path)

    real = [c for c in chapters if not c["is_noise"]]
    return {
        "filename": file.filename,
        "total_files": info["total"],
        "real_chapters": info["real"],
        "noise_count": info["noise"],
        "noise_titles": info["noise_titles"],
        "preview": [
            {"number": ch["number"], "title": ch["title"], "char_count": ch["char_count"]}
            for ch in real[:10]
        ],
        "total_preview_count": len(real),
    }


@router.post("/extract-epub")
async def extract_epub_chapters(
    file: UploadFile = File(...),
    start_chapter: int = Form(1),
    end_chapter: int = Form(-1),
    format: str = Form("epub"),
):
    """Extract a chapter range from an EPUB and return as a new EPUB or TXT file."""
    import tempfile
    import os
    from fastapi.responses import Response, PlainTextResponse
    from app.modules.indexer.epub_parser import parse_epub
    from app.utils.epub_builder import build_epub

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        all_chapters = parse_epub(tmp_path)
    finally:
        os.unlink(tmp_path)

    real = [c for c in all_chapters if not c["is_noise"]]
    total = len(real)

    if end_chapter == -1 or end_chapter > total:
        end_chapter = total
    if start_chapter < 1:
        start_chapter = 1
    if start_chapter > end_chapter:
        start_chapter = end_chapter

    selected = real[start_chapter - 1 : end_chapter]
    if not selected:
        from fastapi import HTTPException
        raise HTTPException(400, "No chapters in selected range")

    base_name = (file.filename or "unknown").rsplit(".", 1)[0]
    range_title = f"{base_name} 第{start_chapter}-{end_chapter}章"

    if format == "txt":
        lines = []
        for ch in selected:
            body = ch["text"]
            if body.startswith(ch["title"]):
                body = body[len(ch["title"]):].strip()
            lines.append(ch["title"])
            lines.append("")
            lines.append(body)
            lines.append("")
            lines.append("")
        txt = "\n".join(lines).strip()
        safe_name = base_name.encode('ascii', 'ignore').decode('ascii').replace(' ', '_') or 'extracted'
        return PlainTextResponse(
            content=txt,
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}_{start_chapter}-{end_chapter}.txt"',
                "Content-Type": "text/plain; charset=utf-8",
            },
        )
    else:
        epub_bytes = build_epub(
            title=range_title,
            author="Extracted",
            chapters=[(ch["title"], ch["text"]) for ch in selected],
        )
        safe_name = base_name.encode('ascii', 'ignore').decode('ascii').replace(' ', '_') or 'extracted'
        return Response(
            content=epub_bytes,
            media_type="application/epub+zip",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}_{start_chapter}-{end_chapter}.epub"',
            },
        )


@router.post("/upload", response_model=UploadResponse)
async def upload_book(file: UploadFile = File(...)):
    filename = file.filename or "unknown"
    content = await file.read()

    # Detect format
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

    if ext == "epub":
        import tempfile
        from app.modules.indexer.epub_parser import parse_epub

        # Save EPUB to temp file for parsing
        with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            chapters = parse_epub(tmp_path)
        finally:
            import os
            os.unlink(tmp_path)

        real_chapters = [c for c in chapters if not c["is_noise"]]
        title = filename.rsplit(".", 1)[0]
        book_id = await storage.create_book_epub(title, chapters)

        return UploadResponse(book_id=book_id, new_chapters=len(real_chapters), format="epub")
    else:
        # TXT upload (existing flow)
        text = content.decode("utf-8")
        title = filename.rsplit(".", 1)[0]
        book_id = await storage.create_book(title, text)

        from app.modules.indexer.chapter_parser import parse_chapters
        chapters = parse_chapters(text)
        return UploadResponse(book_id=book_id, new_chapters=len(chapters), format="txt")


@router.get("/")
async def list_books():
    books = await storage.list_books()
    result = []
    for b in books:
        book_id = b["book_id"]
        # Try to get chapter count from chapters.json first, then parse original
        chapters = await storage.load_chapters(book_id)
        if chapters:
            total = sum(1 for c in chapters if not c.get("is_noise"))
        else:
            from app.modules.indexer.chapter_parser import parse_chapters
            original = await storage.load_original(book_id)
            if original:
                total = len(parse_chapters(original))
            else:
                total = 0
        result.append({**b, "total_chapters": total})
    return result


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
    status = await storage.get_status(book_id)

    # Add chapter count
    chapters = await storage.load_chapters(book_id)
    if chapters:
        total = sum(1 for c in chapters if not c.get("is_noise"))
    else:
        from app.modules.indexer.chapter_parser import parse_chapters
        original = await storage.load_original(book_id)
        if original:
            total = len(parse_chapters(original))
        else:
            total = 0
    status["total_chapters"] = total
    return status


@router.get("/{book_id}/chapters")
async def get_chapter_preview(book_id: str):
    """返回章节列表，用于预览和选择。

    Query params:
        start: 起始章节号 (1-based, default 1)
        end: 结束章节号 (1-based, default -1 means all)
    """
    chapters = await storage.load_chapters(book_id)
    if chapters is None:
        # TXT books: parse from original
        from app.modules.indexer.chapter_parser import parse_chapters
        original = await storage.load_original(book_id)
        if not original:
            raise HTTPException(404, "Book not found")
        chapters = parse_chapters(original)

    # Filter out noise chapters for EPUB
    clean_chapters = [c for c in chapters if not c.get("is_noise")]

    return {
        "book_id": book_id,
        "total_chapters": len(clean_chapters),
        "chapters": [
            {
                "number": c.get("number", i + 1),
                "title": c["title"],
                "char_count": c.get("char_count", len(c.get("text", ""))),
            }
            for i, c in enumerate(clean_chapters)
        ],
    }


@router.delete("/{book_id}")
async def delete_book(book_id: str):
    await storage.delete_book(book_id)
    return {"status": "ok"}
