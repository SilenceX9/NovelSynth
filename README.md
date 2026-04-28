# NovelSynth

[![License](https://img.shields.io/badge/License-CC%20BY--NC%204.0-orange.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![Version](https://img.shields.io/badge/Version-0.3.0-green.svg)]()

> **AI-powered novel condensation engine.** Distill million-word web novels into clean "main plot + expandable summaries" versions—removing filler, preserving essence.

---

## Features

### 🧠 Auto Global Context

Reads the entire novel and extracts:
- Character profiles & relationship networks
- Main plot threads & story arcs
- Key items, foreshadowings & world-building elements

Condensation isn't blind deletion—it's intelligent filtering based on global understanding.

### ✂️ Mixed Dehydration (v0.3)

Each paragraph is classified by LLM into a hybrid output:

- **【KEEP】** — Main plot, key dialogues, core settings → preserved verbatim
- **【SUMMARIZE】** — Side plots, scene descriptions → condensed to 1-2 sentences, expandable to original text

**Reading experience**: Main story flows naturally; summaries can be expanded on demand. Achieves **60-80% compression**—reading 100 chapters feels like reading 20-30.

### 💬 Built-in Q&A Assistant

Ask questions while reading: *"Who is this character?"* *"What happened to that foreshadowing?"* Answers are grounded in the original text and global context, with chapter references.

### 📚 Incremental Updates

Append new chapters to ongoing novels. Only new content is re-indexed/condensed, preserving existing results.

### ⏸️ Pause/Resume with Checkpoints

Long-running tasks can be paused and resumed from where they left off.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11+ / FastAPI (async) |
| LLM | OpenAI-compatible API (any endpoint) |
| Storage | SQLite + Local filesystem |
| Frontend | Vanilla HTML/CSS/JS (zero build chain) |

---

## Quick Start

### Installation

```bash
git clone https://github.com/your-username/novelsynth.git
cd novelsynth
pip install -e .
```

### Configure LLM

After starting the server, configure your LLM provider in the settings page.

**Supported providers**:
- OpenAI (official)
- DeepSeek (cost-effective, recommended)
- Any OpenAI-compatible endpoint (Ollama, proxies, etc.)

**Config example**:
```json
{
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "api_key": "your-api-key-here"
}
```

### Start Server

```bash
# Using startup script (recommended)
./start.sh

# Custom port
PORT=8080 ./start.sh

# Direct uvicorn
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open http://localhost:8765 in your browser.

---

## Usage Workflow

**Step 1 — Upload**

Upload `.txt` or `.epub` files on the home page. Files are automatically split into chapters.

**Step 2 — Index**

Click "Start Indexing" to extract:
- Character list & relationships
- Plot summary & story arcs
- Key items & foreshadowings

View results in the "Global Context" page.

**Step 3 — Condense**

Click "Start Dehydration" to process each chapter:
- LLM analyzes paragraph importance
- Outputs hybrid 【KEEP】+【SUMMARIZE】 format
- Generates expandable structured results

Pause anytime; resume from checkpoint automatically.

**Step 4 — Read & Ask**

Open the reader:
- KEEP content displayed directly
- SUMMARIZE content expands to original on click
- Q&A box in sidebar for instant queries

**Step 5 — Export**

Export condensed results as:
- `.txt` plain text
- `.epub` ebook (opens in any reader)

---

## API Reference

| Endpoint | Description |
|----------|-------------|
| `POST /api/books/upload` | Upload novel file |
| `GET /api/books/` | List all books |
| `POST /api/books/{id}/append` | Append new chapters |
| `POST /api/index/{id}/start` | Start global indexing |
| `POST /api/dehydrate/{id}/start` | Start condensation |
| `POST /api/dehydrate/{id}/pause` | Pause condensation |
| `GET /api/dehydrate/{id}/status` | Get condensation progress |
| `GET /api/dehydrate/{id}/export/txt` | Export as TXT |
| `GET /api/dehydrate/{id}/export/epub` | Export as EPUB |
| `POST /api/qa/{id}/ask` | Q&A query |

---

## Development

See [DEV.md](DEV.md) for:
- Project structure
- Data flow diagrams
- Dehydration model & prompt design
- Storage layout
- Customization (compression rate, concurrency, etc.)

---

## License

**CC BY-NC 4.0** (Attribution-NonCommercial 4.0 International)

- ✅ Personal learning & research
- ✅ Open-source references (with attribution)
- ❌ Commercial use requires written authorization

See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- Reader UI design inspired by [Legado](https://github.com/gedoor/legado), [Readest](https://github.com/readest/readest), [Foliate](https://github.com/johnfactotum/foliate), [LNReader](https://github.com/lnreader/lnreader)
- Project structure guided by CodeStable workflow framework