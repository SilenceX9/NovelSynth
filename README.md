# AI 网文脱水机 / AI Novel Dehydrator

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![Version](https://img.shields.io/badge/Version-0.1.0-green.svg)]()

> 将百万字长篇网文精简为"主线保留 + 支线摘要"的纯净版，去除注水废话，同时提供伴随式智能问答助手。
>
> Condense million-word web novels into a clean "main plot preserved + side plots summarized" version, removing filler content, with a built-in AI Q&A assistant.

---

## 核心亮点 / Key Features

### 🧠 全局上下文自动构建
通读全本，自动提取核心角色清单、人物关系网、主线剧情脉络、关键道具与伏笔库，输出结构化档案。脱水不是盲目删减，而是基于全局理解的智能筛选。

**Auto Global Context** — Reads the entire novel, extracts character profiles, relationship networks, main plot threads, key items and foreshadowings into a structured archive. Dehydration is smart filtering based on global understanding, not blind deletion.

### ✂️ 三层智能脱水
每个段落经过 LLM 判定为三层之一：
- **保留层**：主线推进、关键对话、核心设定，原文保留
- **摘要层**：支线剧情、场景描写，浓缩为一两句摘要
- **删除层**：注水废话、重复描述、无关闲聊，直接剔除

实测压缩率 **60-80%**，读 100 章 ≈ 读 20-30 章。

**Three-Layer Smart Dehydration** — Each block classified by LLM:
- **KEEP**: Main plot, key dialogues, core settings — preserved as-is
- **SUMMARIZE**: Side plots, scene descriptions — condensed to 1-2 sentences
- **DELETE**: Filler, repetition, irrelevant chat — removed entirely

Achieves **60-80% compression**. Reading 100 chapters feels like reading 20-30.

### 💬 伴随式问答助手
阅读脱水版时随时提问："这个人物是谁？""前面提到的伏笔后来怎样了？"系统基于原版全文和全局上下文检索回答，并标注参考章节。

**Built-in Q&A Assistant** — Ask anything while reading: "Who is this character?" "What happened to that foreshadowing?" Answers are grounded in the original text and global context, with chapter references.

### 📚 增量更新支持
追更的小说可以追加新章节，系统自动识别新增内容，只重新索引和脱水新增部分，已有结果保留。

**Incremental Updates** — Append new chapters to ongoing novels. The system detects new content and only re-indexes/dehydrates the additions, preserving existing results.

### ⏸️ 暂停/恢复与断点续传
长时间任务可随时暂停，恢复后从断点继续，无需重头开始。

**Pause/Resume with Checkpoints** — Long-running tasks can be paused and resumed from where they left off.

---

## 技术架构 / Tech Stack

| 层级 | 技术 | Layer | Tech |
|------|------|-------|------|
| 后端 | Python 3.11+ + FastAPI (async) | Backend | Python 3.11+ + FastAPI |
| LLM | OpenAI 兼容协议（支持任意兼容 endpoint） | LLM | OpenAI-compatible API |
| 存储 | SQLite + 本地文件系统 | Storage | SQLite + Local FS |
| 前端 | 原生 HTML/CSS/JS，零构建链 | Frontend | Vanilla HTML/CSS/JS |

---

## 快速开始 / Quick Start

```bash
# 安装依赖 / Install dependencies
pip install -e .

# 启动服务 / Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 浏览器打开 / Open in browser
open http://localhost:8000
```

在首页上传 `.txt` 格式的小说文件，依次完成索引和脱水后即可阅读。

Upload a `.txt` novel file on the home page, complete indexing and dehydration, then start reading.

---

## 贡献者 / Contributors

| 贡献者 | 贡献内容 |
|--------|----------|
| [gedoor/legado](https://github.com/gedoor/legado) | 章节导航与阅读器交互设计参考 |
| [readest/readest](https://github.com/readest/readest) | 阅读排版与界面风格参考 |
| [johnfactotum/foliate](https://github.com/johnfactotum/foliate) | 阅读体验与深色模式参考 |
| [lnreader/lnreader](https://github.com/lnreader/lnreader) | 侧边栏交互与主题切换参考 |
| Qwen (通义千问) | AI 代码生成与架构设计 |
| Silence | 产品定义、需求设计、测试验证 |

---

## 许可证 / License

本项目采用 MIT License。详见 [LICENSE](LICENSE) 文件。

---

## 致谢 / Acknowledgments

- 前端阅读器 UI 设计灵感来源于 [Legado](https://github.com/gedoor/legado)、[Readest](https://github.com/readest/readest)、[Foliate](https://github.com/johnfactotum/foliate)、[LNReader](https://github.com/lnreader/lnreader) 等开源阅读器项目
- 感谢 CodeStable 工作流管理工具对项目结构的规范指导
