from app.llm_client import LLMClient
from app.llm_config import load_llm_config
from app.models.context import GlobalContext
from app.models.dehydration import BlockResult, Layer
from app.modules.dehydration.prompt import DEHYDRATE_PROMPT

BLOCK_MAX_CHARS = 800


def _llm() -> LLMClient:
    cfg = load_llm_config()
    return LLMClient(base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"])


def split_into_blocks(text: str) -> list[str]:
    """按段落切分，每块不超过 BLOCK_MAX_CHARS，段落边界对齐。"""
    paragraphs = text.split("\n\n")
    blocks = []
    current = []
    current_len = 0

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if current_len + len(p) > BLOCK_MAX_CHARS and current:
            blocks.append("\n\n".join(current))
            current = [p]
            current_len = len(p)
        else:
            current.append(p)
            current_len += len(p)

    if current:
        blocks.append("\n\n".join(current))
    return blocks


async def dehydrate_chapter(
    chapter_text: str,
    context: GlobalContext,
) -> list[BlockResult]:
    """脱水单章。返回每个 block 的判定结果。"""
    blocks = split_into_blocks(chapter_text)
    results = []

    core_names = [c.name for c in context.characters if c.role in ("主角", "配角")]
    foreshadow_descs = [f.description for f in context.foreshadows]

    prompt = DEHYDRATE_PROMPT.format(
        core_characters="、".join(core_names) if core_names else "无",
        main_plot_keywords="、".join(context.main_plot[:10]),
        foreshadows="、".join(foreshadow_descs) if foreshadow_descs else "无",
        key_items="、".join(context.key_items) if context.key_items else "无",
    )

    llm = _llm()
    for block in blocks:
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": block},
        ]
        try:
            data = await llm.chat_json(messages)
            layer = Layer(data["layer"])
            output = data["output"]
        except Exception:
            # fallback: keep on error
            layer = Layer.KEEP
            output = block
        results.append(BlockResult(text=block, layer=layer, output=output))

    return results


def assemble_dehydrated(blocks: list[BlockResult]) -> str:
    """把 block 结果拼接为脱水文本。DELETE 的块跳过。"""
    parts = []
    for b in blocks:
        if b.layer == Layer.DELETE:
            continue
        parts.append(b.output)
    return "\n\n".join(parts)
