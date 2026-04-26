"""Zero-dependency EPUB3 builder using only stdlib. Apple Books compatible."""
import io
import uuid
import zipfile
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

ET.register_namespace("opf", "http://www.idpf.org/2007/opf")
ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
ET.register_namespace("epub", "http://www.idpf.org/2007/ops")

NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""


def _esc(s: str) -> str:
    """Escape for XML content."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _chapter_xhtml(title: str, body: str) -> str:
    """Generate a single chapter XHTML5 file."""
    escaped_title = _esc(title)
    # Convert paragraphs: each \n\n-separated block becomes a <p>
    paragraphs = body.strip().split("\n\n")
    p_html = ""
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        inner = p.replace("\n", "<br/>")
        p_html += f"  <p>{inner}</p>\n"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh">
<head>
  <title>{escaped_title}</title>
  <meta charset="UTF-8"/>
  <style>
@namespace epub "http://www.idpf.org/2007/ops";
body {{ font-family: serif; line-height: 1.8; margin: 2em 1.5em; }}
h2 {{ text-align: center; margin: 1.5em 0 1em; font-size: 1.4em; }}
p {{ text-indent: 2em; margin: 0.5em 0; }}
  </style>
</head>
<body>
  <h2 id="ch-title">{escaped_title}</h2>
{p_html.rstrip()}
</body>
</html>"""


def _toc_xhtml(chapters: list[tuple[str, str]]) -> str:
    """Generate EPUB3 navigation document (TOC)."""
    links = ""
    for i, (title_ch, fname) in enumerate(chapters, 1):
        links += f'      <li><a href="{fname}">{_esc(title_ch)}</a></li>\n'

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh">
<head>
  <title>目录</title>
  <meta charset="UTF-8"/>
  <style>
body {{ font-family: serif; margin: 2em 1.5em; }}
h2 {{ text-align: center; margin-bottom: 1.5em; }}
nav#toc ol {{ list-style: none; padding: 0; }}
nav#toc li {{ margin: 0.6em 0; }}
nav#toc a {{ text-decoration: none; color: #333; }}
  </style>
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h2>目录</h2>
    <ol>
{links.rstrip()}
    </ol>
  </nav>
</body>
</html>"""


def _ncx(chapters: list[tuple[str, str]], title: str) -> str:
    """Generate EPUB2 NCX toc for backward compatibility (Apple Books fallback)."""
    uid = f"urn:uuid:{uuid.uuid4()}"
    nav_points = ""
    for i, (ch_title, fname) in enumerate(chapters, 1):
        nav_points += f"""
    <navPoint id="navPoint-{i}" playOrder="{i}">
      <navLabel><text>{_esc(ch_title)}</text></navLabel>
      <content src="{fname}"/>
    </navPoint>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nc PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{uid}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{_esc(title)}</text></docTitle>
  <navMap>{nav_points}
  </navMap>
</ncx>"""


def _build_opf(title: str, author: str, chapters: list[tuple[str, str]]) -> str:
    """Generate content.opf package document (EPUB3)."""
    uid = f"urn:uuid:{uuid.uuid4()}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest_items = [
        '    <item id="toc" properties="nav" href="toc.xhtml" media-type="application/xhtml+xml"/>',
        '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
    ]
    for ch_title, fname in chapters:
        manifest_items.append(
            f'    <item id="ch-{fname.replace(".xhtml", "")}" href="{fname}" media-type="application/xhtml+xml"/>'
        )

    spine_items = ['    <itemref idref="toc"/>'] + [
        f'    <itemref idref="ch-{fname.replace(".xhtml", "")}"/>' for _, fname in chapters
    ]

    manifest_xml = "\n".join(manifest_items)
    spine_xml = "\n".join(spine_items)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="uid">{uid}</dc:identifier>
    <dc:title id="main-title">{_esc(title)}</dc:title>
    <meta refines="#main-title" property="title-type">main</meta>
    <dc:creator id="creator">{_esc(author)}</dc:creator>
    <dc:language>zh</dc:language>
    <meta property="dcterms:modified">{now}</meta>
    <meta name="cover" content="cover"/>
  </metadata>
  <manifest>
{manifest_xml}
  </manifest>
  <spine toc="ncx" page-progression-direction="ltr">
{spine_xml}
  </spine>
</package>"""


def build_epub(
    title: str,
    author: str,
    chapters: list[tuple[str, str]],
) -> bytes:
    """Build EPUB3 bytes, Apple Books compatible.

    Args:
        title: Book title.
        author: Author name.
        chapters: List of (chapter_title, chapter_body) tuples.
    """
    buf = io.BytesIO()
    non_empty = [(t, b) for t, b in chapters if b.strip()]

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be first and stored uncompressed
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)

        # chapter files
        chapter_fnames = []
        for i, (ch_title, ch_body) in enumerate(non_empty, 1):
            fname = f"chapter_{i:03d}.xhtml"
            chapter_fnames.append((ch_title, fname))
            zf.writestr(f"OEBPS/{fname}", _chapter_xhtml(ch_title, ch_body))

        # EPUB3 navigation document
        zf.writestr("OEBPS/toc.xhtml", _toc_xhtml(chapter_fnames))

        # EPUB2 NCX fallback
        zf.writestr("OEBPS/toc.ncx", _ncx(chapter_fnames, title))

        # content.opf
        zf.writestr("OEBPS/content.opf", _build_opf(title, author, chapter_fnames))

    return buf.getvalue()
