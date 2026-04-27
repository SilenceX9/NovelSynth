# AI 网文脱水机 v0.2 开发交接文档

> 版本：v0.2
> 封版日期：2026-04-27
> 下一个开发者阅读本文档即可快速上手

---

## 1. 项目概述

**核心功能**：将长篇网文精简为"主线保留+支线摘要"的脱水版，同时提供智能问答助手。

**目标用户**：网文读者，想要快速了解剧情主线，跳过注水内容。

**技术栈**：
- 后端：Python 3.14 + FastAPI（async）
- LLM：OpenAI 兼容协议（支持自定义 base_url/model）
- 存储：SQLite（元数据）+ 文件系统（`data/{book_id}/`）
- 前端：原生 HTML + CSS + JS，无构建链

---

## 2. 核心架构

### 2.1 目录结构

```
小说速读/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── llm_client.py        # LLM 调用封装
│   ├── llm_config.py        # LLM 配置加载
│   ├── storage.py           # 存储层（SQLite + 文件）
│   ├── task_manager.py      # 任务状态管理
│   ├── models/              # Pydantic 模型
│   │   ├── context.py       # 全局上下文模型
│   │   ├── dehydration.py   # 脱水结果模型
│   │   └── qa.py            # 问答模型
│   ├── modules/             # 业务模块
│   │   ├── indexer/         # 索引模块（提取角色/伏笔等）
│   │   ├── dehydration/     # 脱水模块（核心）
│   │   └── qa_assistant/    # 问答助手模块
│   ├── routes/              # API 路由
│   │   ├── books.py         # 书籍管理
│   │   ├── dehydrate.py     # 脱水任务
│   │   ├── tasks.py         # 任务状态查询
│   │   ├── qa.py            # 问答接口
│   │   ├── settings.py      # 设置保存
│   │   └── index.py         # 静态页面路由
│   ├── static/              # 前端页面
│   │   ├── index.html       # 主页（上传书籍）
│   │   ├── task.html        # 任务进度页
│   │   ├── read.html        # 阅读器页面
│   │   └── settings.html    # LLM 配置页
│   └── utils/               # 工具函数
│       ├── chapter_parser.py # 章节解析
│       └── text_utils.py    # 文本处理
├── data/                    # 数据目录（运行时生成）
│   ├── app.db               # SQLite 元数据库
│   ├── llm_config.json      # LLM 配置
│   └── {book_id}/           # 每本书的数据
│       ├── original.txt     # 原文
│       ├── context.json     # 全局上下文
│       ├── dehydrated.txt   # 脱水文本
│       ├── dehydrated_blocks.json  # 结构化脱水数据
│       └── dehydrate_checkpoint.json  # 脱水进度检查点
├── docs/                    # 文档目录
├── codestable/              # CodeStable 工作流目录
└── test/                    # 测试文件
```

### 2.2 数据流

```
用户上传小说 → 索引模块提取上下文 → 脱水模块处理 → 阅读器展示
                    ↓                      ↓
              context.json          dehydrated_blocks.json
              （角色/伏笔等）         （分层文本块）
```

---

## 3. 核心模块详解

### 3.1 索引模块（indexer）

**功能**：从原文提取全局上下文（核心角色、主线关键词、伏笔、关键道具）

**入口文件**：`app/modules/indexer/service.py`

**关键函数**：
- `index_book(book_id, original_text)` → 返回 `GlobalContext`

**输出文件**：`data/{book_id}/context.json`

**注意**：索引任务会调用 LLM，需要消耗 token。

### 3.2 脱水模块（dehydration）

**功能**：将原文分段分类（keep/delete/summarize），生成脱水版本

**入口文件**：`app/modules/dehydration/service.py`

**核心函数**：
- `dehydrate_chapter(chapter_text, context)` → 返回 `list[BlockResult]`
- `start_or_resume_dehydrate(book_id, context, chapters)` → 启动脱水任务
- `assemble_structured(blocks)` → 生成 JSON 结构化数据

**关键逻辑**（`dehydrate_chapter`）：
1. 先分割原文成片段（每段 50-150 字）
2. 构建分类 prompt 发送给 LLM
3. 根据 LLM 返回的分类结果构建输出
4. `summarize` 类型会保存 `original` 字段用于展开显示原文

**输出文件**：
- `dehydrated.txt`：纯文本
- `dehydrated_blocks.json`：结构化数据（含 layer、text、original、chapter）

### 3.3 问答模块（qa_assistant）

**功能**：基于原文和上下文回答用户问题

**入口文件**：`app/modules/qa_assistant/service.py`

**核心函数**：
- `ask_question(question, original_text, context)` → 返回 `AskResponse`

**检索策略**：简单 keyword 检索，从原文中找相关段落

---

## 4. 前端页面

### 4.1 主页（index.html）

**功能**：上传小说、查看书籍列表、触发索引/脱水任务

**关键 API**：
- `POST /api/storage/books`：上传书籍
- `POST /api/index/{book_id}/start`：启动索引
- `POST /api/dehydrate/{book_id}/start`：启动脱水

### 4.2 任务页（task.html）

**功能**：显示任务进度、支持暂停/继续、重试失败章节

**关键 API**：
- `GET /api/tasks/book/{book_id}`：获取任务状态

**特性**：
- 支持增量脱水（只脱水未完成的章节）
- 支持重试失败章节

### 4.3 阅读器（read.html）

**功能**：展示脱水文本、支持摘要展开、问答助手

**核心渲染逻辑**：
- `renderStructured(blocks)`：渲染结构化脱水数据
- `keep` 类型直接显示原文
- `summarize` 类型显示摘要，点击展开原文

**关键 CSS 类**：
- `.block-keep`：保留段落样式
- `.single-summarize`：单个摘要样式
- `.note-group`：多个摘要聚合样式
- `.note-original`：展开的原文样式

---

## 5. API 接口清单

| 路径 | 方法 | 功能 |
|------|------|------|
| `/api/storage/books` | GET/POST | 书籍列表/上传 |
| `/api/storage/books/{book_id}` | DELETE | 删除书籍 |
| `/api/index/{book_id}/start` | POST | 启动索引 |
| `/api/dehydrate/{book_id}/start` | POST | 启动脱水（支持 start_chapter/end_chapter） |
| `/api/dehydrate/{book_id}/pause` | POST | 暂停脱水 |
| `/api/dehydrate/{book_id}/resume` | POST | 继续脱水 |
| `/api/dehydrate/{book_id}/retry` | POST | 重试失败章节 |
| `/api/tasks/book/{book_id}` | GET | 获取任务状态 |
| `/api/dehydrate/{book_id}/output` | GET | 获取脱水输出 |
| `/api/qa/{book_id}/ask` | POST | 问答接口 |
| `/api/settings/llm` | GET/POST | LLM 配置 |

---

## 6. 已知问题与待优化

### 6.1 已知问题

1. **脱水率不稳定**：LLM 偏向保留内容，实际脱水率约 47%，未达到设计目标 70%
   - 原因：Gemini Flash Lite 模型不够激进
   - 解决思路：更换更强模型，或在代码中添加强制删除逻辑

2. **段落分割精度**：分割函数 `_split_into_segments` 基于句号分割，可能导致语义断裂
   - 解决思路：改用语义分割或更精细的规则

3. **问答检索粗糙**：当前只用 keyword 检索，可能漏掉重要段落
   - 解决思路：改用向量检索或 LLM 辅助检索

### 6.2 待优化功能

1. **批量脱水**：支持一次性脱水多本书
2. **导出功能**：支持导出脱水文本为 TXT/PDF
3. **阅读进度同步**：支持跨设备同步阅读进度
4. **离线模式**：支持本地 LLM（如 Ollama）
5. **EPUB 支持**：目前只支持 TXT，需要添加 EPUB 解析

---

## 7. 开发注意事项

### 7.1 环境要求

- Python 3.14（使用了最新的 async 特性）
- 需要 httpx、aiosqlite、pydantic、pydantic-settings

### 7.2 启动命令

```bash
uvicorn app.main:app --reload --port 8000
```

### 7.3 测试命令

暂无自动化测试，手动测试流程：
1. 启动服务
2. 打开 http://localhost:8000
3. 上传测试文件（`test/剑来_前20章.txt`）
4. 执行索引 → 执行脱水 → 阅读器查看

### 7.4 数据清理

删除书籍数据：
```bash
rm -rf data/{book_id}/
```

重置所有数据：
```bash
rm -rf data/
```

---

## 8. 代码风格约定

1. **异步优先**：所有 I/O 操作使用 async
2. **类型标注**：使用 Python 类型标注
3. **无注释原则**：代码自解释，不写多余注释
4. **前端无构建**：原生 HTML/CSS/JS，不引入框架

---

## 9. 下一个开发者快速上手

### 9.1 第一次运行

```bash
# 1. 安装依赖
pip install fastapi uvicorn httpx aiosqlite pydantic pydantic-settings

# 2. 启动服务
uvicorn app.main:app --reload --port 8000

# 3. 打开浏览器
open http://localhost:8000

# 4. 配置 LLM
# 打开 http://localhost:8000/settings.html
# 填入 base_url、api_key、model
```

### 9.2 理解脱水流程

阅读以下文件顺序：
1. `app/routes/dehydrate.py`：API 入口
2. `app/modules/dehydration/service.py`：核心逻辑
3. `app/static/read.html`：前端渲染

### 9.3 修改脱水逻辑

修改 `app/modules/dehydration/service.py` 中的 `dehydrate_chapter` 函数。

关键参数：
- `_split_into_segments`：调整 `min_chars`、`max_chars` 控制片段长度
- `classify_prompt`：调整提示词控制删除率

---

## 10. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v0.1 | 2026-04-25 | MVP：基础脱水功能 |
| v0.2 | 2026-04-27 | 三层分类、摘要展开、问答助手、增量脱水 |

---

## 11. 联系与资源

- 项目仓库：本地目录
- 设计文档：`codestable/architecture/ARCHITECTURE.md`
- API 参考：`codestable/architecture/API_REFERENCE.md`

---

*文档结束。下一个开发者有问题可直接参考本文档。*