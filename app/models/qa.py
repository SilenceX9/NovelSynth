from pydantic import BaseModel


class AskRequest(BaseModel):
    book_id: str
    question: str


class AskResponse(BaseModel):
    answer: str
    source_chapters: list[int]
