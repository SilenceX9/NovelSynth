from pydantic import BaseModel
from typing import Optional


class CharacterProfile(BaseModel):
    name: str
    role: str  # 主角/配角/反派/其他
    relationships: list[str] = []
    first_chapter: int
    last_chapter: int


class Foreshadow(BaseModel):
    description: str
    setup_chapter: int
    resolved: bool = False


class GlobalContext(BaseModel):
    book_title: str
    total_chapters: int
    characters: list[CharacterProfile]
    main_plot: list[str]
    foreshadows: list[Foreshadow]
    key_items: list[str]


class PartialContext(BaseModel):
    """单批 LLM 提取结果"""
    characters: list[dict]
    plot: list[str]
    foreshadows: list[dict]
    key_items: list[str]


class IndexResponse(BaseModel):
    book_id: str
    context: Optional[GlobalContext] = None
    status: str  # "completed" / "failed"
    error: Optional[str] = None
