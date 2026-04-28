#!/usr/bin/env python3
"""Extract first N non-noise chapters from an EPUB file.

Usage:
    python3 tools/extract_chapters.py <epub_path> [--count N] [--output PATH] [--stats]

Examples:
    # Show chapter count and noise titles
    python3 tools/extract_chapters.py 小说归档/剑来.epub --stats

    # Extract first 20 chapters to stdout
    python3 tools/extract_chapters.py 小说归档/剑来.epub --count 20

    # Extract first 30 chapters to a file
    python3 tools/extract_chapters.py 小说归档/剑来.epub --count 30 --output test/剑来_前30章.txt
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.modules.indexer.epub_parser import parse_epub, count_chapters


def main():
    parser = argparse.ArgumentParser(description="Extract chapters from EPUB")
    parser.add_argument("epub_path", help="Path to EPUB file")
    parser.add_argument("--count", "-n", type=int, default=None,
                        help="Number of non-noise chapters to extract (default: all)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output file path (default: stdout)")
    parser.add_argument("--stats", "-s", action="store_true",
                        help="Show chapter statistics only, no extraction")
    args = parser.parse_args()

    epub_path = Path(args.epub_path)
    if not epub_path.exists():
        print(f"Error: file not found: {args.epub_path}", file=sys.stderr)
        sys.exit(1)

    if args.stats:
        info = count_chapters(str(epub_path))
        print(f"文件: {epub_path.name}")
        print(f"总文件数: {info['total']}")
        print(f"正文章节: {info['real']}")
        print(f"噪声章节: {info['noise']}")
        if info["noise_titles"]:
            print(f"\n噪声章节列表:")
            for t in info["noise_titles"]:
                print(f"  - {t}")
        return

    all_chapters = parse_epub(str(epub_path))
    # parse_epub returns all items; filter to real chapters only
    real_chapters = [ch for ch in all_chapters if not ch["is_noise"]]

    if not real_chapters:
        print("Error: no real chapters found", file=sys.stderr)
        sys.exit(1)

    count = args.count if args.count else len(real_chapters)
    selected = real_chapters[:count]

    output_lines = []
    for ch in selected:
        output_lines.append(ch["title"])
        output_lines.append("")
        # Strip the title from text body (it's already present from <h2>)
        body = ch["text"]
        if body.startswith(ch["title"]):
            body = body[len(ch["title"]):].strip()
        output_lines.append(body)
        output_lines.append("")
        output_lines.append("")

    result = "\n".join(output_lines).strip()

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
        total_chars = sum(ch["char_count"] for ch in selected)
        print(f"已提取 {len(selected)} 章 → {output_path}")
        print(f"总字数: {total_chars:,}")
        noise_count = sum(1 for ch in all_chapters if ch["is_noise"])
        if noise_count:
            print(f"已跳过 {noise_count} 个噪声章节")
    else:
        print(result)


if __name__ == "__main__":
    main()
