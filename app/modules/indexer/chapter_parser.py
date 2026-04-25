import re

CHAPTER_RE = re.compile(r"^第[零一二三四五六七八九十百千万〇0-9]+[章节回卷]")

AUTO_SPLIT_CHARS = 3000


def parse_chapters(text: str) -> list[dict]:
    """按章节标题切分。失败则降级为按固定字数切。"""
    lines = text.split("\n")
    chapters = []
    current_title = None
    current_lines = []

    for line in lines:
        stripped = line.strip()
        if CHAPTER_RE.match(stripped):
            # save previous chapter
            if current_title is not None:
                chapters.append({
                    "number": len(chapters) + 1,
                    "title": current_title,
                    "text": "\n".join(current_lines).strip(),
                })
            current_title = stripped
            current_lines = []
        elif current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        chapters.append({
            "number": len(chapters) + 1,
            "title": current_title,
            "text": "\n".join(current_lines).strip(),
        })

    if chapters:
        return chapters

    # fallback: auto-split by character count
    return _auto_split(text)


def _auto_split(text: str) -> list[dict]:
    chunks = []
    for i in range(0, len(text), AUTO_SPLIT_CHARS):
        chunk = text[i : i + AUTO_SPLIT_CHARS]
        if chunk.strip():
            chunks.append({
                "number": len(chunks) + 1,
                "title": f"自动分段 {len(chunks)+1}",
                "text": chunk.strip(),
                "auto_split": True,
            })
    return chunks
