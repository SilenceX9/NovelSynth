from app.llm_client import LLMClient
from app.llm_config import load_llm_config
from app.models.context import GlobalContext
from app.models.qa import AskResponse

QA_PROMPT = """你是网文阅读助手，帮助读者理解小说内容。

回答要求：
1. **直接回答问题**，不要开场白（"根据原文"、"我来回答"等）
2. **分点说明**，用「•」列出关键信息
3. **引用原文关键句**时用引号标注
4. **不确定的内容**明确说「原文未提及」
5. **控制在3-5句话**，简洁明了

上下文：
角色：{context_summary}

相关原文：
{retrieved_text}
"""


def _llm() -> LLMClient:
    cfg = load_llm_config()
    return LLMClient(base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"])


def search_chapters(original_text: str, question: str, context: GlobalContext) -> list[tuple[int, str]]:
    """简单 keyword 检索：从原版全文中找相关段落，返回 (章节号, 段落) 列表。"""
    from app.modules.indexer.chapter_parser import parse_chapters
    chapters = parse_chapters(original_text)

    keywords = [c.name for c in context.characters if c.name in question]
    keywords += [item for item in context.key_items if item in question]
    if not keywords:
        keywords = question.split()

    results = []
    for ch in chapters:
        if any(kw in ch["text"] for kw in keywords if kw):
            snippet = ch["text"][:500]
            results.append((ch["number"], snippet))

    return results[:5]


async def ask_question(
    question: str,
    original_text: str,
    context: GlobalContext,
) -> AskResponse:
    related = search_chapters(original_text, question, context)

    retrieved = "\n\n---\n\n".join(
        f"第{num}章：\n{text}" for num, text in related
    )
    if not retrieved:
        retrieved = "（未检索到相关原文）"

    context_summary = (
        f"{', '.join(c.name for c in context.characters[:10])}\n"
        f"主线：{', '.join(context.main_plot[:5])}\n"
        f"伏笔：{', '.join(f.description for f in context.foreshadows[:5])}"
    )

    messages = [
        {"role": "system", "content": QA_PROMPT.format(
            context_summary=context_summary,
            retrieved_text=retrieved,
        )},
        {"role": "user", "content": question},
    ]

    llm = _llm()
    answer = await llm.chat(messages, temperature=0.3)
    source_chapters = [num for num, _ in related] if related else []

    return AskResponse(answer=answer, source_chapters=source_chapters)