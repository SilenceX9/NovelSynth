# NovelSynth

[![License](https://img.shields.io/badge/License-CC%20BY--NC%204.0-orange.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![Version](https://img.shields.io/badge/Version-0.3.0-green.svg)]()

**[English Version ↓](#english-version)**

---

## 中文版

> **AI 驱动的小说浓缩引擎**。将百万字长篇网文蒸馏为"主线保留 + 可展开摘要"的纯净版——去除注水，保留精华。

---

### 核心亮点

#### 🧠 全局上下文自动构建

通读全本，自动提取：
- 角色清单与人物关系网
- 主线剧情脉络与故事弧线
- 关键道具、伏笔与世界观设定

浓缩不是盲目删减，而是基于全局理解的智能筛选。

#### ✂️ 混合脱水模式（v0.3）

每个段落经 LLM 判定后输出混合格式：

- **【保留】** — 主线推进、关键对话、核心设定 → 原文完整保留
- **【概括】** — 支线剧情、场景描写 → 浓缩为 1-2 句，点击展开原文

**阅读体验**：主线流畅阅读，概括部分一键展开，兼顾效率与完整度。实测压缩率 **60-80%**，读 100 章 ≈ 读 20-30 章。

#### 💬 伴随式问答助手

阅读时随时提问："这个角色是谁？""那个伏笔后来怎样了？"回答基于原文与全局上下文，标注参考章节。

#### 📚 增量更新

追加新章节，仅对新内容重新索引/浓缩，已有结果保留。

#### ⏸️ 暂停/续传

长任务可随时暂停，恢复后从断点继续。

---

### 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11+ / FastAPI (async) |
| LLM | OpenAI 兼容协议（任意 endpoint） |
| 存储 | SQLite + 本地文件系统 |
| 前端 | 原生 HTML/CSS/JS（零构建链） |

---

### 快速开始

#### 安装

```bash
git clone https://github.com/SilenceX9/NovelSynth.git
cd NovelSynth
pip install -e .
```

#### 配置 LLM

启动后访问设置页面配置 provider：

**支持**：OpenAI、DeepSeek（性价比高，推荐）、其他 OpenAI 兼容 endpoint（Ollama、代理等）

**配置示例**：
```json
{
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "api_key": "your-api-key-here"
}
```

#### 启动服务

```bash
./start.sh              # 默认 127.0.0.1:8765
PORT=8080 ./start.sh    # 自定义端口
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

浏览器打开 http://localhost:8765

---

### 使用流程

**Step 1 — 上传**

首页点击「上传」，支持 `.txt` 和 `.epub`，自动切分章节。

**Step 2 — 索引**

点击「开始索引」，提取角色、关系、剧情摘要、伏笔库。完成后可在「全局上下文」页查看。

**Step 3 — 脱水**

点击「开始脱水」，逐章分析段落重要性，输出【保留】+【概括】混合格式。可随时暂停，恢复后自动续传。

**Step 4 — 阅读 + 问答**

打开阅读器：保留内容直接展示，概括内容点击展开原文。右下角问答框随时提问。

**Step 5 — 导出**

导出 `.txt` 纯文本或 `.epub` 电子书。

---

### API 端点

| 端点 | 用途 |
|------|------|
| `POST /api/books/upload` | 上传小说 |
| `GET /api/books/` | 书籍列表 |
| `POST /api/books/{id}/append` | 追加章节 |
| `POST /api/index/{id}/start` | 启动索引 |
| `POST /api/dehydrate/{id}/start` | 启动脱水 |
| `POST /api/dehydrate/{id}/pause` | 暂停脱水 |
| `GET /api/dehydrate/{id}/status` | 脱水进度 |
| `GET /api/dehydrate/{id}/export/txt` | 导出 TXT |
| `GET /api/dehydrate/{id}/export/epub` | 导出 EPUB |
| `POST /api/qa/{id}/ask` | 问答 |

---

### 开发文档

详见 [DEV.md](DEV.md)：项目结构、数据流、脱水模型与 Prompt 设计、存储布局、自定义配置等。

---

### 许可证

**CC BY-NC 4.0**（署名-非商业性使用）

- ✅ 个人学习研究
- ✅ 开源引用（需署名）
- ❌ 商用需书面授权

详见 [LICENSE](LICENSE)。

---

### 致谢

- 阅读器 UI 参考 [Legado](https://github.com/gedoor/legado)、[Readest](https://github.com/readest/readest)、[Foliate](https://github.com/johnfactotum/foliate)、[LNReader](https://github.com/lnreader/lnreader)
- 项目结构由 CodeStable 工作流框架指导

---

<br>

---

## English Version

**[中文版本 ↑](#中文版)**

---

> **AI-powered novel condensation engine.** Distill million-word web novels into clean "main plot + expandable summaries" versions—removing filler, preserving essence.

---

### Key Features

#### 🧠 Auto Global Context

Reads the entire novel and extracts:
- Character profiles & relationship networks
- Main plot threads & story arcs
- Key items, foreshadowings & world-building elements

Condensation is intelligent filtering based on global understanding, not blind deletion.

#### ✂️ Mixed Dehydration (v0.3)

Each paragraph classified by LLM into hybrid output:

- **【KEEP】** — Main plot, key dialogues, core settings → preserved verbatim
- **【SUMMARIZE】** — Side plots, scene descriptions → condensed to 1-2 sentences, expandable to original

**Reading experience**: Main story flows naturally; summaries expand on demand. **60-80% compression**—100 chapters feels like 20-30.

#### 💬 Built-in Q&A Assistant

Ask while reading: *"Who is this character?"* *"What happened to that foreshadowing?"* Answers grounded in original text with chapter references.

#### 📚 Incremental Updates

Append new chapters; only new content is re-indexed/condensed.

#### ⏸️ Pause/Resume

Long tasks can be paused and resumed from checkpoint.

---

### Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11+ / FastAPI (async) |
| LLM | OpenAI-compatible API (any endpoint) |
| Storage | SQLite + Local filesystem |
| Frontend | Vanilla HTML/CSS/JS (zero build) |

---

### Quick Start

#### Install

```bash
git clone https://github.com/SilenceX9/NovelSynth.git
cd NovelSynth
pip install -e .
```

#### Configure LLM

Configure provider in settings page after startup.

**Supported**: OpenAI, DeepSeek (cost-effective, recommended), any OpenAI-compatible endpoint (Ollama, proxies, etc.)

**Config example**:
```json
{
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "api_key": "your-api-key-here"
}
```

#### Start Server

```bash
./start.sh              # default 127.0.0.1:8765
PORT=8080 ./start.sh    # custom port
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open http://localhost:8765

---

### Workflow

**Step 1 — Upload**

Upload `.txt` or `.epub` on home page, auto-split into chapters.

**Step 2 — Index**

Click "Start Indexing" to extract characters, relationships, plot summary, foreshadowings. View in "Global Context" page.

**Step 3 — Condense**

Click "Start Dehydration" to analyze paragraphs, output 【KEEP】+【SUMMARIZE】 hybrid. Pause anytime; resume from checkpoint.

**Step 4 — Read & Ask**

Open reader: KEEP content displayed, SUMMARIZE expands to original. Q&A box for instant queries.

**Step 5 — Export**

Export as `.txt` or `.epub`.

---

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/books/upload` | Upload novel |
| `GET /api/books/` | Book list |
| `POST /api/books/{id}/append` | Append chapters |
| `POST /api/index/{id}/start` | Start indexing |
| `POST /api/dehydrate/{id}/start` | Start condensation |
| `POST /api/dehydrate/{id}/pause` | Pause |
| `GET /api/dehydrate/{id}/status` | Progress |
| `GET /api/dehydrate/{id}/export/txt` | Export TXT |
| `GET /api/dehydrate/{id}/export/epub` | Export EPUB |
| `POST /api/qa/{id}/ask` | Q&A |

---

### Development Docs

See [DEV.md](DEV.md) for project structure, data flow, dehydration model & prompt design, storage layout, customization.

---

### License

**CC BY-NC 4.0** (Attribution-NonCommercial)

- ✅ Personal learning & research
- ✅ Open-source references (with attribution)
- ❌ Commercial use requires authorization

See [LICENSE](LICENSE).

---

### Acknowledgments

- Reader UI inspired by [Legado](https://github.com/gedoor/legado), [Readest](https://github.com/readest/readest), [Foliate](https://github.com/johnfactotum/foliate), [LNReader](https://github.com/lnreader/lnreader)
- Project structure guided by CodeStable workflow framework