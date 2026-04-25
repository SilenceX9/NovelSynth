# AI 网文脱水机 — 架构文档

## 系统概览

```
app/
├── main.py                 # FastAPI 入口，挂载 4 个 router + static
├── config.py               # Settings（LLM 连接、batch_size、data_dir）
├── llm_client.py           # 统一 LLM 调用层（OpenAI 兼容协议）
├── storage.py              # 统一存储层（SQLite 元数据 + 文件系统）
├── models/                 # Pydantic 数据模型
│   ├── context.py          # GlobalContext / PartialContext / IndexResponse
│   ├── dehydration.py      # Layer / BlockResult / DehydrateRequest
│   └── qa.py               # AskRequest / AskResponse
├── modules/
│   ├── indexer/            # 全局索引模块
│   │   ├── chapter_parser.py  # 正则章节解析 + 自动分段 fallback
│   │   ├── extractor.py       # 分批 LLM 提取（角色/剧情/伏笔/道具）
│   │   ├── merger.py          # 多批 PartialContext 合并去重
│   │   └── service.py         # 索引编排入口
│   ├── dehydration/        # 智能脱水模块
│   │   ├── prompt.py          # 脱水判定 prompt 模板
│   │   └── service.py         # 分块 → LLM 判定 → 拼接
│   └── qa_assistant/       # Q&A 助手模块
│       └── service.py         # 关键词检索 + LLM 回答生成
├── routes/
│   ├── books.py            # /api/books/upload, /api/books/{id}/status
│   ├── index.py            # /api/index/{id}, /api/index/{id}/context
│   ├── dehydrate.py        # /api/dehydrate/{id}, progress, output
│   └── qa.py               # /api/qa/ask
└── static/                 # Web UI（原生 HTML/CSS/JS，无构建链）
    ├── index.html          # 上传 + 索引页
    ├── read.html           # 脱水阅读 + Q&A 页
    ├── context.html        # 全局上下文查看页
    ├── app.css
    └── app.js
```

## 三模块架构

### 1. 全局索引模块（Global Indexer）

**职责**：从全书原文中提取结构化全局上下文。

**流程**：
1. `chapter_parser.parse_chapters()` — 用正则 `^第[零一二...]+[章节回卷]` 解析章节标题；若无匹配章节，降级为每 3000 字符自动分段。
2. `extractor.extract_batch()` — 每批 10 章（`settings.batch_size`），LLM 以 JSON 格式提取：角色（名字/定位/关系/出场章节）、主线剧情（每章一句话）、伏笔（描述/出场章节）、关键道具。
3. `merger.merge_contexts()` — 合并多批结果：角色去重合并（出场 < 3 章的非主角降级为"其他"）、伏笔跨批出现标记为 resolved、剧情按序拼接。

**输出**：一份 `GlobalContext` JSON，持久化到 `data/{book_id}/context.json`。

### 2. 智能脱水模块（Smart Dehydrator）

**职责**：基于全局上下文，逐章判定每个文本块的保留/压缩/删除策略。

**流程**：
1. 将单章按段落边界切分为 500-800 字符的文本块（`split_into_blocks`）。
2. 对每个块调用 LLM，传入上下文档案（核心角色名、主线关键词、伏笔、关键道具）。
3. LLM 判定三层之一：
   - `KEEP`：核心角色对话、主线转折、生死危机、情感场景、伏笔/道具相关
   - `SUMMARIZE`：支线任务、升级重复、非核心角色戏份，输出 `[注：XXX]` 格式
   - `DELETE`：纯环境描写、重复招式说明、路人反应、水字数，直接剔除
4. 非 DELETE 块按序拼接，全章脱水后保存。

**降级策略**：LLM 调用失败时默认 KEEP 原块，避免数据丢失。

**输出**：`data/{book_id}/dehydrated.txt`。

### 3. Q&A 助手模块（Q&A Assistant）

**职责**：基于关键词检索 + 全局上下文，回答读者问题。

**流程**：
1. 从用户问题中提取关键词（优先匹配角色名、关键道具名，无匹配则分词）。
2. 在原版全文的章节中搜索匹配关键词的段落，取前 5 个相关片段（每章截取前 500 字符）。
3. 将全局上下文摘要（核心角色、主线、伏笔、道具）与检索片段一起送入 LLM，生成回答。
4. 返回回答 + 参考章节号列表。

## 数据流

```
上传 TXT → POST /api/books/upload
              │
              ▼
       data/{book_id}/original.txt
       SQLite: books(book_id, title, indexed=0, dehydrated=0)
              │
              ▼
POST /api/index/{book_id} ──────────────────────────────┐
              │                                          │
              ▼                                          ▼
       chapter_parser → extractor（10章/批）→ merger    │
              │                                          │
              ▼                                          │
       GlobalContext → data/{book_id}/context.json      │
       SQLite: indexed=1                                │
              │                                          │
              ▼                                          │
POST /api/dehydrate/{book_id} ← 依赖 context.json ──────┘
              │
              ▼
       逐章 split_into_blocks → LLM 逐块判定 → assemble
              │
              ▼
       data/{book_id}/dehydrated.txt
       SQLite: dehydrated=1
              │
              ▼
GET  /api/dehydrate/{book_id}/output  → 返回脱水全文
POST /api/qa/ask                       → 关键词检索 + LLM 回答
```

**模块依赖关系**：脱水依赖索引（需要 context.json），Q&A 依赖索引（需要 context.json）+ 原文（需要 original.txt）。

## 核心数据实体：GlobalContext

`GlobalContext` 是整个系统的枢纽，被脱水模块和 Q&A 模块共同消费。

```python
class GlobalContext(BaseModel):
    book_title: str                     # 书名
    total_chapters: int                 # 总章节数
    characters: list[CharacterProfile]  # 角色档案
    main_plot: list[str]                # 主线剧情（每章一句话）
    foreshadows: list[Foreshadow]       # 伏笔列表
    key_items: list[str]                # 关键道具名

class CharacterProfile(BaseModel):
    name: str                           # 角色名
    role: str                           # 主角/配角/反派/其他
    relationships: list[str]            # 关系描述
    first_chapter: int                  # 首次出场章节号
    last_chapter: int                   # 最后出场章节号

class Foreshadow(BaseModel):
    description: str                    # 伏笔描述
    setup_chapter: int                  # 埋下伏笔的章节号
    resolved: bool                      # 是否已揭晓
```

**存储位置**：`data/{book_id}/context.json`（JSON 格式，UTF-8，indent=2）。

**生命周期**：
1. 由 `indexer.merger.merge_contexts()` 生成
2. 通过 `storage.save_context()` 持久化
3. 脱水模块通过 `storage.load_context()` 读取，提取核心角色名/伏笔/道具注入 prompt
4. Q&A 模块通过 `storage.load_context()` 读取，用于关键词提取和上下文摘要

## LLM 调用约束

### 协议

- 使用 OpenAI 兼容协议（`{base_url}/v1/chat/completions`）
- 通过 `Settings` 统一配置 `llm_base_url`、`llm_model`、`llm_api_key`
- 由 `LLMClient` 类统一封装，不直接在其他模块调 httpx

### 调用方法

| 方法 | 用途 | temperature |
|------|------|-------------|
| `chat(messages, temperature)` | 通用文本对话 | 默认 0.3 |
| `chat_json(messages, temperature, max_retries)` | 强制 JSON 输出，自动剥离 markdown code fence | 默认 0.3 |

### 重试策略

- `chat_json()` 内置重试：默认 `max_retries=2`，非 JSON 返回时自动重试
- 脱水模块：单块判定失败时降级为 `KEEP`，不阻塞整章
- 索引模块：批次提取失败会向上抛出，触发 route 层 catch 返回 `status="failed"`
- 超时：httpx 默认 120 秒

### 温度选择

- 索引提取：0.3（结构化输出，需要稳定性）
- 脱水判定：0.3（判定一致）
- Q&A 回答：0.5（适度创造性）

## Web UI 三页结构

所有页面使用原生 HTML + CSS + JS，无构建链，由 FastAPI 的 `StaticFiles` 直接提供。

### 页面 1：上传/索引页（`index.html`）

- 上传 TXT 文件（拖拽或点击）
- 调用 `POST /api/books/upload` 获取 `book_id`
- 自动跳转或手动触发 `POST /api/index/{book_id}`
- 显示索引进度和结果

### 页面 2：阅读+Q&A 页（`read.html`）

- 左侧：脱水全文渲染（`GET /api/dehydrate/{book_id}/output`）
- 右侧/底部：Q&A 对话框（`POST /api/qa/ask`）
- 显示参考章节号

### 页面 3：上下文查看页（`context.html`）

- 角色列表（名字/定位/出场范围/关系）
- 主线剧情时间线
- 伏笔列表（状态：未揭晓/已揭晓）
- 关键道具列表

## 存储布局

```
data/
├── app.db                           # SQLite：books 表（book_id, title, indexed, dehydrated）
└── {book_id}/                       # 每本书一个目录
    ├── original.txt                 # 原版全文
    ├── context.json                 # 全局上下文（GlobalContext）
    └── dehydrated.txt               # 脱水全文
```
