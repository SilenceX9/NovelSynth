from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel

from app.storage import Storage

router = APIRouter(prefix="/api/books", tags=["books"])
storage = Storage()


class UploadResponse(BaseModel):
    book_id: str


@router.post("/upload", response_model=UploadResponse)
async def upload_book(file: UploadFile = File(...)):
    content = await file.read()
    text = content.decode("utf-8")
    title = file.filename or "unknown"
    book_id = await storage.create_book(title, text)
    return UploadResponse(book_id=book_id)


@router.get("/{book_id}/status")
async def get_status(book_id: str):
    return await storage.get_status(book_id)
