from app.config import settings
from app.models.context import GlobalContext
from app.modules.indexer.chapter_parser import parse_chapters
from app.modules.indexer.extractor import extract_batch
from app.modules.indexer.merger import merge_contexts


async def index_novel(book_id: str, original_text: str, book_title: str) -> GlobalContext:
    """全书索引：章节解析 → 分批提取 → 合并去重。"""
    chapters = parse_chapters(original_text)
    batch_size = settings.batch_size
    partials = []

    for i in range(0, len(chapters), batch_size):
        batch_end = min(i + batch_size, len(chapters))
        partial = await extract_batch(chapters, i, batch_end)
        partials.append(partial)

    ctx = merge_contexts(partials, book_title)
    return ctx
