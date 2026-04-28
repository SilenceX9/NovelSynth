# AI 网文脱水机 / AI Novel Dehydrator

[![License](https://img.shields.io/badge/License-CC%20BY--NC%204.0-orange.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![Version](https://img.shields.io/badge/Version-0.3.0-green.svg)]()

> 将百万字长篇网文精简为"主线保留 + 支线摘要"的纯净版，去除注水废话，同时提供伴随式智能问答助手。
>
> Condense million-word web novels into a clean "main plot preserved + side plots summarized" version, removing filler content, with a built-in AI Q&A assistant.

---

## 核心亮点 / Key Features

### 🧠 全局上下文自动构建

通读全本，自动提取核心角色清单、人物关系网、主线剧情脉络、关键道具与伏笔库，输出结构化档案。脱水不是盲目删减，而是基于全局理解的智能筛选。

**Auto Global Context** — Reads the entire novel, extracts character profiles, relationship networks, main plot threads, key items and foreshadowings into a structured archive. Dehydration is smart filtering based on global understanding, not blind deletion.

### ✂️ 混合脱水模式（v0.3 新特性）

每个段落经过 LLM 判定后输出混合格式：

- **保留层【KEEP】**：主线推进、关键对话、核心设定 → 原文完整保留
- **概括层【SUMMARIZE】**：支线剧情、场景描写 → 浓缩为 1-2 句话，点击可展开原文

**阅读体验**：主线内容流畅阅读，概括部分一键展开查看原文，兼顾效率与完整度。

实测压缩率 **60-80%**，读 100 章 ≈ 读 20-30 章。

**Mixed Dehydration (v0.3)** — Each paragraph classified by LLM into:

- **KEEP**: Main plot, key dialogues, core settings — preserved verbatim
- **SUMMARIZE**: Side plots, scene descriptions — condensed to 1-2 sentences, expandable to original

**Reading experience**: Main story flows naturally; summaries can be expanded on demand. Achieves **60-80% compression**.

### 💬 伴随式问答助手

阅读脱水版时随时提问："这个人物是谁？""前面提到的伏笔后来怎样了？"系统基于原版全文和全局上下文检索回答，并标注参考章节。

**Built-in Q&A Assistant** — Ask anything while reading: "Who is this character?" "What happened to that foreshadowing?" Answers are grounded in the original text and global context, with chapter references.

### 📚 增量更新支持

追更的小说可以追加新章节，系统自动识别新增内容，只重新索引和脱水新增部分，已有结果保留。

**Incremental Updates** — Append new chapters to ongoing novels. Only new content is re-indexed/dehydrated, preserving existing results.

### ⏸️ 暂停/恢复与断点续传

长时间任务可随时暂停，恢复后从断点继续，无需重头开始。

**Pause/Resume with Checkpoints** — Long-running tasks can be paused and resumed from where they left off.

---

## 技术架构 / Tech Stack

| 层级 | 技术 | Layer | Tech |
|------|------|-------|------|
| 后端 | Python 3.11+ + FastAPI (async) | Backend | Python 3.11+ + FastAPI |
| LLM | OpenAI 兼容协议（支持任意 endpoint） | LLM | OpenAI-compatible API |
| 存储 | SQLite + 本地文件系统 | Storage | SQLite + Local FS |
| 前端 | 原生 HTML/CSS/JS，零构建链 | Frontend | Vanilla HTML/CSS/JS |

---

## 使用指南 / Usage Guide

### 1. 安装 / Installation

```bash
# 克隆仓库 / Clone repository
git clone https://github.com/your-username/novel-dehydrator.git
cd novel-dehydrator

# 安装依赖 / Install dependencies
pip install -e .
```

### 2. 配置 LLM / Configure LLM

启动后访问设置页面配置你的 LLM provider：

**支持的 Provider**：
- OpenAI（官方）
- DeepSeek（性价比高，推荐）
- 其他 OpenAI 兼容 endpoint（如本地 Ollama、各类代理）

**配置示例**：
```json
{
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "api_key": "your-api-key-here"
}
```

### 3. 启动服务 / Start Server

```bash
# 使用启动脚本（推荐）
./start.sh

# 或自定义端口
PORT=8080 ./start.sh

# 或直接 uvicorn
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

浏览器打开 http://localhost:8765

### 4. 处理流程 / Processing Workflow

**Step 1 — 上传小说**

首页点击「上传」，支持 `.txt` 和 `.epub` 格式。文件会自动切分为章节。

**Step 2 — 全局索引**

点击「开始索引」，系统将：
- 提取核心角色清单
- 构建人物关系网
- 生成主线剧情摘要
- 建立关键道具/伏笔库

索引完成后可查看「全局上下文」页面。

**Step 3 — 智能脱水**

点击「开始脱水」，系统将：
- 逐章调用 LLM 分析段落重要性
- 输出【保留】+【概括】混合格式
- 生成可展开的结构化结果

脱水过程中可随时暂停，恢复后自动从断点继续。

**Step 4 — 阅读 + 问答**

打开「阅读器」页面：
- 保留内容直接展示
- 概括内容点击展开原文
- 右下角问答框随时提问

**Step 5 — 导出**

脱水完成后可导出：
- `.txt` 纯文本版
- `.epub` 电子书版（支持阅读器打开）

---

## API 端点 / API Endpoints

| 端点 | 用途 |
|------|------|
| `POST /api/books/upload` | 上传小说文件 |
| `GET /api/books/` | 书籍列表 |
| `POST /api/books/{id}/append` | 追加新章节 |
| `POST /api/index/{id}/start` | 启动全局索引 |
| `POST /api/dehydrate/{id}/start` | 启动脱水 |
| `POST /api/dehydrate/{id}/pause` | 暂停脱水 |
| `GET /api/dehydrate/{id}/status` | 脱水进度 |
| `GET /api/dehydrate/{id}/export/txt` | 导出 TXT |
| `GET /api/dehydrate/{id}/export/epub` | 导出 EPUB |
| `POST /api/qa/{id}/ask` | 问答接口 |

---

## 开发文档 / Development Docs

详见 [DEV.md](DEV.md)，包含：
- 项目结构详解
- 数据流说明
- 脱水模型与 Prompt 设计
- 存储布局
- 自定义配置（压缩率、并行度等）

---

## 贡献者 / Contributors

| 贡献者 | 贡献内容 |
|--------|----------|
| [gedoor/legado](https://github.com/gedoor/legado) | 章节导航与阅读器交互设计参考 |
| [readest/readest](https://github.com/readest/readest) | 阅读排版与界面风格参考 |
| [johnfactotum/foliate](https://github.com/johnfactotum/foliate) | 阅读体验与深色模式参考 |
| [lnreader/lnreader](https://github.com/lnreader/lnreader) | 侧边栏交互与主题切换参考 |
| Claude (Anthropic) | AI 代码生成与架构设计 |

---

## 许可证 / License

本项目采用 **CC BY-NC 4.0** 协议（署名-非商业性使用 4.0 国际）。

- ✅ 个人学习、研究使用
- ✅ 开源项目引用（需署名）
- ❌ 商业用途需书面授权

详见 [LICENSE](LICENSE) 文件。

---

## 致谢 / Acknowledgments

- 前端阅读器 UI 设计灵感来源于 Legado、Readest、Foliate、LNReader 等开源阅读器项目
- 感谢 CodeStable 工作流管理工具对项目结构的规范指导