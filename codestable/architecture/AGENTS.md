# Agent 开发约定

适用于所有参与本项目开发的 AI Agent（Claude Code 等）。

## 文件组织

### 模块目录结构

```
app/modules/{module}/
```

- `modules/` 下每个模块是一个子目录，目录名使用小写+下划线（如 `indexer/`、`qa_assistant/`、`dehydration/`）。
- 模块内约定：
  - `service.py` — 模块编排入口（对外暴露的 async 函数）
  - `prompt.py` — prompt 模板（与业务逻辑分离）
  - `extractor.py` / `merger.py` / `chapter_parser.py` 等 — 按职责拆分

### 路由目录

```
app/routes/
```

- 每个路由文件对应一个 API 前缀，文件名与 `prefix` 一致。
- 路由文件只负责：参数校验、调用 service、返回响应。不包含业务逻辑。

### 模型目录

```
app/models/
```

- 每个 Pydantic 模型放在对应模块的模型文件中。
- `context.py` — 索引相关模型（GlobalContext、PartialContext、IndexResponse）
- `dehydration.py` — 脱水相关模型（Layer、BlockResult）
- `qa.py` — Q&A 相关模型（AskRequest、AskResponse）

### 顶层文件

| 文件 | 职责 |
|------|------|
| `main.py` | FastAPI app 创建、router 注册、static 挂载 |
| `config.py` | Settings（环境变量读取） |
| `llm_client.py` | LLM 调用统一封装 |
| `storage.py` | 文件 + SQLite 存储统一封装 |

## 存储约定

### 目录结构

```
data/{book_id}/
├── original.txt      # 原版全文（上传时写入）
├── context.json      # 全局上下文（索引完成后写入）
└── dehydrated.txt    # 脱水全文（脱水完成后写入）
```

- `book_id` 由 `uuid4().hex[:12]` 生成，12 位十六进制字符串。
- 新增文件一律放在对应 `book_id` 目录下，不要跨目录存放。
- `data/app.db` 是 SQLite 数据库，存储书籍元数据（标题、索引状态、脱水状态）。

### 读写规则

- 原文文件通过 `storage.load_original()` / `storage.save_original()` 操作。
- 上下文通过 `storage.load_context()` / `storage.save_context()` 操作，模型为 `GlobalContext`。
- 脱水结果通过 `storage.load_dehydrated()` / `storage.save_dehydrated()` 操作。
- 状态标记通过 `storage.get_status()` / `storage.mark_indexed()` / `storage.mark_dehydrated()` 操作。
- 不要绕过 `Storage` 类直接操作文件路径（除非在 `Storage` 内部）。

## 前端约定

### 技术栈

- 原生 HTML + CSS + JS，**不使用任何构建工具或框架**（无 React、Vue、Webpack、Vite）。
- 由 FastAPI `StaticFiles` 直接提供，挂载在 `/`。

### 文件结构

```
app/static/
├── index.html     # 上传 + 索引页（入口）
├── read.html      # 脱水阅读 + Q&A 页
├── context.html   # 全局上下文查看页
├── app.css        # 公共样式
└── app.js         # 公共 JS 工具函数
```

### 交互约定

- 每个页面独立工作，通过 URL 参数或 `localStorage` 传递 `book_id`。
- API 调用使用 `fetch()`，不使用第三方 HTTP 库。
- 错误提示直接显示在页面内，不要 `alert()`。
- 新增页面放在 `app/static/` 下，在 `main.py` 中无需额外注册（`StaticFiles` 自动服务）。

## LLM 调用约定

- 所有 LLM 调用必须通过 `app/llm_client.py` 中的 `LLMClient` 类。
- 不要在业务代码中直接 import `httpx` 调 OpenAI 接口。
- 需要 JSON 输出时使用 `chat_json()`，不要自己解析。
- Prompt 模板放在对应模块的 `prompt.py` 中，不要硬编码在 service 函数里。

## 新增模块 Checklist

1. 在 `app/modules/` 下建目录，目录名小写+下划线。
2. 建 `service.py` 作为编排入口。
3. 需要 prompt 的建 `prompt.py`。
4. 需要新数据模型的在 `app/models/` 下建新文件或追加到现有文件。
5. 在 `app/routes/` 下建路由文件，注册到 `main.py`。
