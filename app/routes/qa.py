from fastapi import APIRouter, HTTPException

from app.models.qa import AskRequest, AskResponse
from app.modules.qa_assistant.service import ask_question
from app.storage import Storage

router = APIRouter(prefix="/api/qa", tags=["qa"])
storage = Storage()


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    original = await storage.load_original(req.book_id)
    if not original:
        raise HTTPException(404, "Book not found")

    ctx = await storage.load_context(req.book_id)
    if ctx is None:
        raise HTTPException(404, "Context not found. Please index the book first.")

    return await ask_question(req.question, original, ctx)
