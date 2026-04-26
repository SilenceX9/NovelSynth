# 开发指南 / Development Guide

> 本文档帮助新对话窗口快速理解项目结构并继续开发。

## 项目概述

AI 网文脱水机 — 将长篇网文精简为主线保留+支线摘要的纯净版，附带伴随式问答助手。

**当前版本**: v0.1.0  
**最后更新**: 2026-04-26

---

## 项目结构

```
.
├── app/
│   ├── main.py                 # FastAPI 入口，挂载路由和静态文件
│   ├── config.py               # Pydantic Settings，读取环境变量
│   ├── storage.py              # SQLite + 文件系统存储层
│   ├── task_manager.py         # 任务状态机（运行/暂停/完成/失败）+ 历史记录
│   ├── llm_client.py           # LLM 调用封装（OpenAI 兼容协议）
│   ├── llm_config.py           # 运行时 LLM 配置（base_url / model / api_key）
│   ├── models/                 # Pydantic 数据模型
│   │   ├── context.py          # GlobalContext / PartialContext / CharacterProfile
│   │   ├── dehydration.py      # BlockResult / Layer (KEEP/SUMMARIZE/DELETE)
│   │   └── qa.py               # QARequest / QAResponse
│   ├── modules/
│   │   ├── indexer/            # 模块一：全局索引
│   │   │   ├── chapter_parser.py   # 章节切分（正则 + 自动分段 fallback）
│   │   │   ├── extractor.py        # 批量 LLM 提取上下文
│   │   │   ├── merger.py           # 多批 PartialContext 合并
│   │   │   └── service.py          # 任务执行 + 增量索引
│   │   ├── dehydration/        # 模块二：智能脱水
│   │   │   ├── prompt.py           # 脱水 prompt 模板
│   │   │   └── service.py          # 分块脱水 + 增量脱水
│   │   └── qa_assistant/       # 模块三：问答助手
│   │       └── service.py          # 关键词检索 + LLM 回答
│   ├── routes/                 # API 路由
│   │   ├── books.py            # 上传 / 追加 / 删除书籍
│   │   ├── index.py            # 索引相关 API
│   │   ├── dehydrate.py        # 脱水相关 API（含导出 TXT/EPUB）
│   │   ├── qa.py               # 问答 API
│   │   ├── settings.py         # LLM 配置 API
│   │   └── tasks.py            # 任务状态查询
│   ├── static/                 # 前端页面
│   │   ├── index.html          # 首页：上传 + 书籍列表
│   │   ├── task.html           # 任务页：索引/脱水进度 + 历史记录
│   │   ├── read.html           # 阅读器：脱水版 + 章节导航 + Q&A
│   │   ├── context.html        # 全局上下文查看页
│   │   ├── app.js              # 公共 JS 工具
│   │   └── app.css             # 公共 CSS
│   └── utils/
│       └── epub_builder.py     # 零依赖 EPUB3 生成器
├── codestable/                 # CodeStable 工作流文档
│   ├── architecture/           # 架构文档
│   ├── requirements/           # 需求档案
│   ├── features/               # Feature 方案
│   ├── roadmap/                # 路线图
│   └── reference/              # 共享规范
├── data/                       # 运行时数据（已 gitignore）
├── pyproject.toml              # Python 依赖配置
└── README.md                   # 项目说明
```

---

## 核心工作流

### 1. 上传书籍
```
POST /api/books/upload  → 创建 book_id，保存原文到 data/{book_id}/original.txt
```

### 2. 全局索引
```
POST /api/index/{book_id}/start  → 启动索引任务
  ├── 按章节切分文本
  ├── 分批 LLM 提取（每批 10 章）→ 生成 PartialContext
  ├── 合并所有 Partial → GlobalContext
  └── 保存到 data/{book_id}/context.json
```

### 3. 智能脱水
```
POST /api/dehydrate/{book_id}/start  → 启动脱水任务
  ├── 加载 GlobalContext 作为全局参考
  ├── 逐章切分为 block（≤300 字/块）
  ├── LLM 判定每块层级（KEEP / SUMMARIZE / DELETE）
  ├── 生成脱水文本 + 结构化 blocks（含 chapter 索引）
  └── 保存到 data/{book_id}/dehydrated.txt + dehydrated_blocks.json
```

### 4. 阅读 + Q&A
```
前端 read.html:
  ├── 加载 dehydrated_blocks.json 渲染结构化脱水版
  ├── 左侧章节导航（可展开/收起）
  ├── 右侧 Q&A 面板
  └── POST /api/qa/ask → 关键词检索 + LLM 回答
```

### 5. 增量更新
```
POST /api/books/{book_id}/append  → 追加新章节
  ├── 去重（按章节标题）
  ├── 增量索引（只处理新增章节的 batch）
  └── 增量脱水（只处理新增章节）
```

---

## 任务状态机

```
pending → running → done
              ↓
           paused → running → done
              ↓
           failed
```

**关键特性**：
- 每个任务（索引/脱水）有独立的 TaskState 记录
- 任务完成后自动归档到历史记录（task_history 表）
- 支持暂停/恢复（通过 in-memory event + DB 状态）
- 增量运行时只处理新增章节，checkpoint 持久化到磁盘

---

## LLM 配置

运行时通过 `/api/settings/llm` 配置，支持：
- OpenAI / Gemini / DeepSeek / 阿里百炼 / 自定义 endpoint
- 配置存储在 `data/llm_config.json`
- 所有服务在每次调用时读取最新配置

---

## 开发约定

### 后端
- 所有 API 使用 async/await
- 存储层通过 `Storage` 类统一封装
- 任务管理通过 `TaskManager` 统一封装
- LLM 调用通过 `LLMClient` 统一封装，支持重试

### 前端
- 原生 HTML/CSS/JS，无构建工具
- 页面间通过 URL 参数传递 `book_id`
- 公共函数放在 `app.js`
- 公共样式放在 `app.css`，页面特定样式内联

### Git
- 大改动先建版本分支：`v{major}.{minor}.{patch}-feature-name`
- Commit message 用英文，精准描述变更意图
- push 需手动执行，不要自动推送

---

## 常见问题

### Q: 如何添加新的 LLM provider？
A: 在 `app/llm_config.py` 的 `DEFAULT_PROVIDERS` 中添加配置，前端 `index.html` 的 provider 下拉菜单同步添加选项。

### Q: 如何修改脱水策略？
A: 修改 `app/modules/dehydration/prompt.py` 中的 `DEHYDRATE_PROMPT` 模板，调整 `BLOCK_MAX_CHARS` 常量控制块大小。

### Q: 如何添加新的导出格式？
A: 在 `app/routes/dehydrate.py` 中添加新 endpoint，参考 `export_txt` 和 `export_epub` 的实现。

### Q: 增量索引为什么 tokens=0？
A: 如果新增章节的 batch 与已有 batch 重叠（即章节仍在已有的 batch 范围内），partial context 会直接从磁盘加载而不触发新的 LLM 调用，因此 tokens=0。这是预期行为。

---

## 下一步可能的方向

- [ ] 支持 EPUB/PDF 上传（当前仅支持 TXT）
- [ ] Q&A 改为向量检索（当前为关键词匹配）
- [ ] 多用户支持 + 登录认证
- [ ] 阅读进度云端同步（当前为 localStorage）
- [ ] 脱水策略可配置化（自定义 prompt / 参数）
- [ ] 批量处理多本书
- [ ] 阅读统计（阅读时长、进度等）
