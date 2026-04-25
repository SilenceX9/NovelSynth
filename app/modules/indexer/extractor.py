from app.llm_client import LLMClient
from app.llm_config import load_llm_config
from app.models.context import PartialContext


def _llm() -> LLMClient:
    cfg = load_llm_config()
    return LLMClient(base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"])


EXTRACT_PROMPT = """你是一个网文分析助手。阅读以下小说章节，提取以下信息：

1. 核心角色（出现 2 次以上的人物）：姓名、角色定位（主角/配角/反派/其他）、与其他角色的关系、在本批中出场的章节号
2. 主线剧情：每章用一句话概括本章最重要的事件
3. 伏笔：暗示了但尚未揭晓的悬念、神秘物品、未交代的身世等
4. 关键道具：有特殊功能的物品

只输出 JSON，不要输出任何其他内容：
{
  "characters": [{"name": "角色名", "role": "主角/配角/反派/其他", "relationships": ["关系描述"], "chapters": [章节号]}],
  "plot": ["第1章：一句话概括", "第2章：一句话概括"],
  "foreshadows": [{"description": "伏笔描述", "chapters": [章节号]}],
  "key_items": ["道具名"]
}

以下是第 {start}-{end} 章的内容：

{chapter_texts}
"""


async def extract_batch(chapters: list[dict], batch_start: int, batch_end: int) -> PartialContext:
    batch = chapters[batch_start:batch_end]
    chapter_texts = "\n\n---\n\n".join(
        f"第{ch['number']}章 {ch['title']}\n{ch['text']}" for ch in batch
    )
    prompt = EXTRACT_PROMPT.format(
        start=batch_start + 1,
        end=batch_end,
        chapter_texts=chapter_texts,
    )
    llm = _llm()
    data = await llm.chat_json([{"role": "user", "content": prompt}])
    return PartialContext.model_validate(data)
