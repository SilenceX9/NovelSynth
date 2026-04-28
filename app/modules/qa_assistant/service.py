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


def _tokenize(text: str) -> set[str]:
    """Simple chinese text tokenization for keyword matching."""
    import re
    tokens = set()
    # Individual characters as unigrams for CJK matching
    chinese_chars = re.findall(r'[一-鿿]', text)
    tokens.update(chinese_chars)
    return tokens


def search_chapters(original_text: str, question: str, context: GlobalContext) -> list[tuple[int, str]]:
    """Scored keyword retrieval: ranks chapters by relevance to question + context."""
    from app.modules.indexer.chapter_parser import parse_chapters
    chapters = parse_chapters(original_text)

    # Build keyword candidates from context
    char_names = [c.name for c in context.characters]
    foreshadow_terms = [f.description for f in context.foreshadows]
    all_context_terms = char_names + context.key_items + context.main_plot + foreshadow_terms

    # Filter to terms that overlap with the question
    q_tokens = _tokenize(question)
    relevant_terms = [t for t in all_context_terms if _tokenize(t) & q_tokens]

    if not relevant_terms:
        relevant_terms = [t for t in question.split() if len(t) >= 2]

    if not relevant_terms:
        return []

    # Score each chapter by keyword hit count
    scored = []
    for ch in chapters:
        ch_text = ch["text"]
        score = sum(1 for kw in relevant_terms if kw in ch_text)
        if score > 0:
            snippet = ch_text[:500]
            scored.append((score, ch["number"], snippet))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [(num, snippet) for _, num, snippet in scored[:5]]


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