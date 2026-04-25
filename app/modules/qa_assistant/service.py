from app.llm_client import LLMClient
from app.models.context import GlobalContext
from app.models.qa import AskResponse

QA_PROMPT = """你是网文阅读助手。基于以下原文片段和全局上下文，回答用户的问题。

如果检索到的原文与问题无关，请基于全局上下文中的角色/伏笔信息尽力回答。
回答时注明参考了哪些章节。

全局上下文：
{context_summary}

检索到的原文片段：
{retrieved_text}
"""

llm = LLMClient()


def search_chapters(original_text: str, question: str, context: GlobalContext) -> list[tuple[int, str]]:
    """简单 keyword 检索：从原版全文中找相关段落，返回 (章节号, 段落) 列表。"""
    import re

    # split original text by chapters if possible
    from app.modules.indexer.chapter_parser import parse_chapters
    chapters = parse_chapters(original_text)

    # extract keywords from question (simple: just use question words)
    keywords = [c.name for c in context.characters if c.name in question]
    keywords += [item for item in context.key_items if item in question]
    if not keywords:
        keywords = question.split()

    results = []
    for ch in chapters:
        if any(kw in ch["text"] for kw in keywords if kw):
            # take first 500 chars of matching chapter
            snippet = ch["text"][:500]
            results.append((ch["number"], snippet))

    return results[:5]  # top 5


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
        f"核心角色：{', '.join(c.name for c in context.characters[:10])}\n"
        f"主线：{', '.join(context.main_plot[:10])}\n"
        f"伏笔：{', '.join(f.description for f in context.foreshadows)}\n"
        f"关键道具：{', '.join(context.key_items)}"
    )

    messages = [
        {"role": "system", "content": QA_PROMPT.format(
            context_summary=context_summary,
            retrieved_text=retrieved,
        )},
        {"role": "user", "content": question},
    ]

    answer = await llm.chat(messages, temperature=0.5)
    source_chapters = [num for num, _ in related] if related else []

    return AskResponse(answer=answer, source_chapters=source_chapters)
