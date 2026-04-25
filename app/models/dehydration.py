from pydantic import BaseModel
from enum import Enum


class Layer(str, Enum):
    KEEP = "keep"
    SUMMARIZE = "summarize"
    DELETE = "delete"


class BlockResult(BaseModel):
    text: str
    layer: Layer
    output: str


class DehydrateRequest(BaseModel):
    book_id: str
    chapter_number: int
    chapter_text: str


class DehydrateResponse(BaseModel):
    book_id: str
    chapter_number: int
    blocks: list[BlockResult]
    dehydrated_text: str
