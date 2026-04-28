# 开发文档

## 快速启动

```bash
./start.sh           # 默认 127.0.0.1:8765
PORT=8080 ./start.sh # 自定义端口
```

首次运行自动安装依赖。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+, FastAPI (async), uvicorn |
| LLM | OpenAI 兼容协议，`LLMClient` 统一封装 |
| 存储 | SQLite (`data/app.db`) + 文件系统 (`data/{book_id}/`) |
| 前端 | 原生 HTML/CSS/JS，无构建链 |
| 依赖 | httpx, aiosqlite, pydantic, pydantic-settings |

## 项目结构

```
app/
├── main.py              # FastAPI 入口，路由挂载
├── config.py            # 全局配置（路径等）
├── llm_client.py        # LLM 调用封装（超时/重试/token 统计）
├── llm_config.py        # 用户 LLM 配置读写
├── storage.py           # 文件 + SQLite 数据存取
├── task_manager.py      # 异步任务状态机（暂停/恢复/断点）
├── models/
│   ├── context.py       # GlobalContext（角色/世界观摘要）
│   └── dehydration.py   # Layer, BlockResult 数据模型
├── modules/
│   ├── indexer/
│   │   ├── chapter_parser.py  # 正文章节切分
│   │   ├── epub_parser.py     # EPUB 解析
│   │   └── service.py         # 索引任务（角色提取/上下文构建）
│   ├── dehydration/
│   │   └── service.py         # 脱水核心：prompt + parse + 并行执行
│   └── qa_assistant/
│       └── service.py         # 伴随式问答
├── routes/
│   ├── books.py         # 上传/列表/导出
│   ├── index.py         # 索引 API
│   ├── dehydrate.py     # 脱水 API
│   ├── tasks.py         # 任务状态 API
│   ├── qa.py            # 问答 API
│   └── settings.py      # LLM 配置 API
├── static/
│   ├── index.html       # 首页（上传/书籍列表）
│   ├── task.html        # 任务管理（索引/脱水进度）
│   ├── read.html        # 阅读器（混合块渲染 + 问答）
│   └── context.html     # 全局上下文查看
└── utils/
    └── epub_builder.py  # EPUB 导出
```

## 核心数据流

```
EPUB/TXT 上传 → 章节切分(parse_chapters) → 全局索引(角色提取)
                                            ↓
                              脱水(dehydrate_chapter)
                              LLM 输出【保留】+【概括】混合格式
                              parser 拆分为多 BlockResult
                                            ↓
                              阅读器渲染(renderStructured)
                              keep 块原文展示 / summarize 块可展开原文
```

## 脱水模型

### BlockResult

```python
class Layer(str, Enum):
    KEEP = "keep"       # 原文保留，前端直接展示
    SUMMARIZE = "summarize"  # 概括，前端折叠 + 点击展开原文

class BlockResult:
    text: str           # 展示文本
    layer: Layer        # keep / summarize
    output: str         # 同 text
    original: str|None  # SUMMARIZE 块的独立原文（来自 LLM 输出的 <原> 标签）
    paragraph: int      # 段落序号，用于合并连续 keep 块
```

### 脱水 Prompt 设计

LLM 输出格式：
```
【保留】
<从原文逐字摘取的关键段落>

【概括】
<一两句话概括，承上启下保持叙事连贯>
<原>
<此处被删的原文段落>
</原>
```

- 第 1-15 章（世界观铺设期）保留 40-50%
- 第 16 章起保留 25-30%
- parser (`_parse_mixed_blocks`) 用正则拆分标记，提取 `<原>` 为独立 original

### 并行策略

- `MAX_DEHYDRATE_CONCURRENCY = 5`（5 章并行）
- 每章最多重试 3 次
- 断点续跑：`dehydrate_checkpoint.json` 记录已完成章节

## 存储布局

```
data/
├── app.db                        # 书籍元数据 + 任务状态
├── llm_config.json               # 用户 LLM 配置
└── {book_id}/
    ├── original.txt              # 原书上文
    ├── chapters.json             # 章节列表 [{title, text, is_noise}]
    ├── context.json              # GlobalContext
    ├── dehydrated.txt            # 脱水纯文本
    ├── dehydrated_blocks.json    # 结构化 BlockResult 列表
    ├── dehydrated_chapters.json  # 分章脱水结果 [{title, text}]
    ├── dehydrate_checkpoint.json # 断点 {completed: [idx], failed: []}
    └── dehydrate_stats.json      # 统计信息
```

## API 关键端点

| 端点 | 用途 |
|---|---|
| `POST /api/books/upload` | 上传 TXT/EPUB |
| `GET /api/books/` | 书籍列表 |
| `POST /api/books/{id}/append` | 追加章节 |
| `POST /api/dehydrate/{id}/start?start_chapter=&end_chapter=` | 启动/继续脱水 |
| `POST /api/dehydrate/{id}/restart` | 重新脱水（清 checkpoint） |
| `GET /api/dehydrate/{id}/status` | 脱水进度 |
| `GET /api/dehydrate/{id}/structured` | 获取结构化 BlockResult |
| `GET /api/dehydrate/{id}/export/txt` | 导出脱水 TXT |
| `GET /api/dehydrate/{id}/export/epub` | 导出脱水 EPUB |
| `GET /api/tasks/book/{id}` | 任务页综合状态 |
| `POST /api/qa/{id}/ask` | 问答 |

## 开发约定

- 使用 CodeStable 工作流管理 feature 生命周期
- Feature 目录：`codestable/feature/{slug}/`（含 design.md + checklist.yaml + acceptance.md）
- 架构文档：`codestable/architecture/`
- Commit 风格：英文简洁描述，release commit 用 `release: vX.Y - description` 格式

## 常见调整

### 调整脱水压缩率

编辑 `app/modules/dehydration/service.py` 中的 prompt：
- `chapter_number <= 15` 控制前期保留比例
- `keep_target` 控制目标保留百分比

### 切换 LLM

前端设置页面或直接编辑 `data/llm_config.json`：
```json
{"provider": "deepseek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-v4-flash", "api_key": "sk-xxx"}
```

### 调整并行度

修改 `service.py` 顶部的 `MAX_DEHYDRATE_CONCURRENCY`。

### 清空数据重来

```bash
rm -rf data/{book_id}/     # 删除单本书
rm -rf data/               # 删除所有数据（保留代码）
```
