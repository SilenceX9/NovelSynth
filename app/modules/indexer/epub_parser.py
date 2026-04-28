"""EPUB chapter extraction with noise filtering."""

import re
import zipfile
from pathlib import Path

# Noise patterns — titles matching these are not story content
NOISE_KEYWORDS = [
    '感言', '请假', '聊几句', '通知', '推荐本书', '广告', '打赏',
    '月票', '求订阅', '盟主', '百盟', '千盟', '万赏', '上架',
    '完本感言', '后记', '新书', '吐槽', '闲聊', '解释一下', '道歉',
    '关于本书', '说一下', '说说', '汇报', '请假条', '写在',
    '求票', '感谢', '致谢', '上架感言', '完结感言',
]

# Non-story file patterns in the EPF spine
NON_STORY_PATTERNS = [
    'coverpage', 'copyright', 'ver-page', 'introdution', 'cover',
    'title', 'copyright', 'about', 'acknowledgement', 'prologue',
    'epilogue', 'announcement', 'notice',
]


def _strip_html(html: str) -> str:
    """Remove HTML tags while preserving paragraph structure."""
    # Strip <head> section entirely to avoid <title> leak
    text = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL)
    # Replace block-level breaks with newlines before stripping tags
    text = re.sub(r'<(?:br\s*/?|/?p|/?div|/h[1-6]|/li|/tr)[^>]*>', '\n', text)
    # Remove remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    # Normalize whitespace: collapse spaces within lines, preserve paragraph breaks
    lines = [re.sub(r'[ \t\r]+', ' ', line).strip() for line in text.split('\n')]
    # Collapse consecutive blank lines to at most one (preserve paragraph separation)
    out = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                out.append('')
                prev_blank = True
        else:
            out.append(line)
            prev_blank = False
    return '\n'.join(out).strip('\n')


def _is_noise(text: str) -> bool:
    """Check if the chapter title is a noise type (author note, ad, etc.).

    Strategy: extract the title first, then check the title for noise keywords.
    This avoids false positives from normal story dialogue containing common words
    like '说说', '道歉', '感谢'.

    Also detects the common EPUB double-title pattern:
    "第X章 标题 第X章 标题" — this repetition is just a formatting artifact,
    not noise. We strip the duplicate before checking.
    """
    # First try to extract title
    title = _extract_chapter_title(text)
    if title:
        # Check the title itself for noise keywords
        return any(k in title for k in NOISE_KEYWORDS)

    # If no title extracted, check the first line
    head = text.split('\n')[0].strip()[:60]
    # Strip double-title pattern: "第X章 Y 第X章 Y" -> "第X章 Y"
    m = re.match(r'^(第[零一二三四五六七八九十百千万〇0-9]+[章节回卷]\s*.+?)\s*\1', head)
    if m:
        head = m.group(1)
    return any(k in head for k in NOISE_KEYWORDS)


def _extract_chapter_title(text: str) -> str | None:
    """Extract a meaningful chapter title from the beginning of the text."""
    first_line = text.split('\n')[0].strip()

    # Pattern 1: "第X章 Title 第X章" (double-title, chapter number repeats)
    m = re.match(r'^(第[零一二三四五六七八九十百千万〇0-9]+[章节回卷])\s*(.+?)\s*\1', first_line)
    if m:
        prefix = m.group(1)
        title_part = m.group(2).strip()
        if title_part and len(title_part) > 1:
            return f"{prefix} {title_part}"
        return prefix

    # Pattern 2: "第X章/节/回/卷 Title" (simple, no repetition)
    m = re.match(r'^(第[零一二三四五六七八九十百千万〇0-9]+[章节回卷])\s*(.+)', first_line)
    if m:
        prefix = m.group(1)
        title_part = m.group(2).strip()
        if title_part and len(title_part) > 1:
            return f"{prefix} {title_part}"
        return prefix

    return None


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    """Find the OPF file path from container.xml."""
    container = zf.read('META-INF/container.xml').decode('utf-8')
    m = re.search(r'full-path="([^"]+)"', container)
    if m:
        return m.group(1)
    # Fallback: search for .opf file
    for name in zf.namelist():
        if name.endswith('.opf'):
            return name
    raise ValueError("No OPF file found in EPUB")


def _parse_opf_spine(zf: zipfile.ZipFile, opf_path: str) -> list[str]:
    """Extract spine item IDs in reading order."""
    opf_dir = str(Path(opf_path).parent)
    opf_content = zf.read(opf_path).decode('utf-8')

    # Build id -> href map from manifest
    manifest = {}
    for m in re.finditer(r'<item\s+id="([^"]+)"\s+href="([^"]+)"', opf_content):
        manifest[m.group(1)] = m.group(2)

    # Get spine items (reading order)
    spine_ids = re.findall(r'<itemref\s+idref="([^"]+)"', opf_content)

    result = []
    for item_id in spine_ids:
        href = manifest.get(item_id)
        if href:
            # Resolve relative path
            if opf_dir:
                full_path = f"{opf_dir}/{href}" if not href.startswith('/') else href.lstrip('/')
            else:
                full_path = href
            result.append(full_path)
    return result


def _clean_double_title(text: str) -> str:
    """Strip duplicated title pattern: "第X章 Y 第X章 Y ..." → "第X章 Y ..." """
    m = re.match(r'^(第[零一二三四五六七八九十百千万〇0-9]+[章节回卷]\s*.+?)\s*\1\s*(.*)', text, re.DOTALL)
    if m:
        return m.group(1) + '\n\n' + m.group(2).strip()
    return text


def parse_epub(epub_path: str) -> list[dict]:
    """Parse an EPUB file and extract chapters with noise filtering.

    Returns list of dicts:
        {"number": int, "title": str, "text": str, "is_noise": bool, "char_count": int}

    Numbering only counts non-noise chapters (real story chapters).
    """
    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        spine_files = _parse_opf_spine(zf, opf_path)

        chapters = []
        real_count = 0

        for fname in spine_files:
            # Skip non-story files
            fname_lower = fname.lower()
            if any(p in fname_lower for p in NON_STORY_PATTERNS):
                continue

            if fname not in zf.namelist():
                continue

            try:
                content = zf.read(fname).decode('utf-8')
            except Exception:
                continue

            text = _strip_html(content)
            # Clean double-title pattern in the text body
            text = _clean_double_title(text)
            if len(text) < 20:  # Skip near-empty files
                continue

            noise = _is_noise(text)
            title = _extract_chapter_title(text)

            if not title:
                # Use first 30 chars as title fallback
                title = text[:30].strip()

            # Strip the extracted title from the text body to avoid duplication
            if title and text.startswith(title):
                text = text[len(title):].strip()

            if not noise:
                real_count += 1

            chapters.append({
                "number": 0 if noise else real_count,
                "title": title,
                "text": text,
                "is_noise": noise,
                "char_count": len(text),
                "file": fname,
            })

        return chapters


def count_chapters(epub_path: str) -> dict:
    """Quick chapter count without loading full text.

    Returns {"total": int, "real": int, "noise": int, "noise_titles": list[str]}
    """
    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        spine_files = _parse_opf_spine(zf, opf_path)

        total = 0
        real = 0
        noise = 0
        noise_titles = []

        for fname in spine_files:
            fname_lower = fname.lower()
            if any(p in fname_lower for p in NON_STORY_PATTERNS):
                continue

            if fname not in zf.namelist():
                continue

            try:
                content = zf.read(fname).decode('utf-8')
            except Exception:
                continue

            text = _strip_html(content)
            if len(text) < 20:
                continue

            total += 1
            if _is_noise(text):
                noise += 1
                title = _extract_chapter_title(text) or text[:30].strip()
                noise_titles.append(title)
            else:
                real += 1

        return {
            "total": total,
            "real": real,
            "noise": noise,
            "noise_titles": noise_titles,
        }
