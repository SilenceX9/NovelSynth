---
doc_type: feature-design
feature: 2026-04-25-novel-dehydrator-mvp
status: approved
summary: AI 网文脱水机 MVP——三模块（全局索引/智能脱水/伴随式 Q&A）端到端实现
tags: [ai-application, content-processing, novel, mvp]
requirement:
roadmap:
roadmap_item:
---

# novel-dehydrator-mvp design

## 第 0 节：术语约定

| 术语 | 定义 | 代码中对应名 |
|---|---|---|
| 全局上下文 | 对全本/整卷小说"通读"后产出的结构化元数据档案 | `GlobalContext` |
| 脱水 | 将网文按保留/摘要/删除三层处理后输出的过程 | `dehydrate()` |
| 脱水版 | 脱水处理后的文本，主线保留原文，支线压缩为摘要 | `dehydrated_text` |
| 原版 | 用户输入的未经处理的原始小说文本 | `original_text` |
| 切片/章 | 脱水时的最小处理单元，可以是一章或固定字数片段 | `ChapterSlice` |
| 保留层 | 脱水判定中"原汁原味保留"的内容 | `Layer.KEEP` |
| 摘要层 | 脱水判定中压缩为 `[注：XXX]` 格式的内容 | `Layer.SUMMARIZE` |
| 删除层 | 脱水判定中直接剔除的内容 | `Layer.DELETE` |
| 角色画像 | 全局索引中单个角色的结构化信息（姓名/阵营/关系/出场章节） | `CharacterProfile` |
| 伏笔 | 需要在后文回收的关键设定或悬念 | `Foreshadow` |

**禁用词**：不使用 "压缩"、"精简"、"改写" 作为脱水过程的术语——这三个词在网文语境中有歧义，统一用"脱水"。

---

## 第 1 节：决策与约束

### 需求摘要

**用户目标**：上传一本长篇网文 → 系统两遍处理后输出脱水版小说 + 可随时提问的 Q&A 助手。

**核心行为**：
1. 上传全本/整卷小说文本（txt/epub）→ 第一遍通读 → 产出全局上下文（角色清单 + 主线脉络 + 伏笔库）
2. 逐章/逐切片脱水 → 输出脱水版文本（保留层原味、摘要层一句话、删除层消失）
3. 阅读脱水版时随时提问 → 系统基于原版全文或全局上下文回答

**成功标准**：
- 10 万字小说全局索引 < 2 分钟（含 LLM 调用时间）
- 单章（3000 字）脱水 < 30 秒
- Q&A 回答基于原版检索，非脱水版
- 摘要层格式固定为 `[注：角色A去了XX地，获得了XX]`

**明确不做**（MVP 边界）：
- 不做多本书管理（一次只处理一本书）
- 不做实时流式脱水输出（整章处理完再返回）
- 不做多轮对话的 Q&A（单轮问答）
- 不做 OCR / 图片识别（纯文本输入）
- 不做多模型自动路由（MVP 固定一个 LLM 后端）

### 挂载点清单

| 挂载点 | 具体位置 | 用途 |
|---|---|---|
| 静态文件 | `app/static/index.html` | 首页：上传文件 + 触发索引 |
| 静态文件 | `app/static/read.html` | 阅读器：显示脱水版 + Q&A 侧栏 |
| 静态文件 | `app/static/context.html` | 全局上下文查看页 |
| 静态文件 | `app/static/app.css`, `app/static/app.js` | 公共样式 + API 调用封装 |
| 路由 | `app/routes/index.py` — POST `/api/index` | 触发全局索引 |
| 路由 | `app/routes/index.py` — GET `/api/index/{book_id}/context` | 获取全局上下文 |
| 路由 | `app/routes/dehydrate.py` — POST `/api/dehydrate` | 触发单章脱水 |
| 路由 | `app/routes/dehydrate.py` — GET `/api/dehydrate/{book_id}/output` | 获取脱水版全文 |
| 路由 | `app/routes/qa.py` — POST `/api/qa/ask` | Q&A 提问 |
| 存储 | `data/{book_id}/original.txt` | 原版全文存储路径 |
| 存储 | `data/{book_id}/context.json` | 全局上下文 JSON |
| 存储 | `data/{book_id}/dehydrated.txt` | 脱水版全文 |
| 配置 | `.env` — `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | LLM 后端配置 |
| DB | `data/app.db` — SQLite，book 元数据表 | 书籍索引记录 |

### 复杂度档位

本项目走 **可读性 = team、性能 = reasonable、健壮性 = L2** 默认档位。无偏离。

### 关键决策

**D1：架构选型——FastAPI + 直接 LLM API 调用（不用 Dify 编排）**
- 原因：MVP 阶段三模块链路简单、线性，不需要 Dify 的可视化编排。直接 Python 调用 LLM API 更灵活，后续想切 Dify 只需替换 `llm_client` 层
- 被拒方案：Dify 工作流编排（MVP 过度设计；且 Dify Docker 会额外占 ~1G 内存，在 16G Mac 上影响其他工作）

**D2：切片方式——按原文章节边界切分，不按固定字数硬切**
- 原因：网文天然有章节结构，按章节切能保证脱水上下文完整。硬切可能把一个情节拦腰斩断
- 边界：如果单章 > 15000 字，自动按段落二次切为子切片，处理后再拼接

**D3：脱水判定——LLM 按区块分类 + 对应处理，不整段一次性生成**
- 原因：一次性让 LLM "脱水整章"容易丢失细节。改为先分区块（每 500-800 字一块），逐块判定保留/摘要/删除，再拼接输出
- 风险：区块边界可能切断对话或情节 → 在区块切分时按段落边界对齐

**D4：Q&A 数据源——基于原版全文 + 全局上下文检索，不基于脱水版**
- 原因：脱水版信息有损，无法回答细节问题。原版全文保证回答完整性，全局上下文加速角色/伏笔相关查询

**D5：存储——本地文件系统 + SQLite，不用向量数据库**
- 原因：MVP 阶段数据量小（一本网文 + 上下文档案），SQLite 足够。全文检索用简单的段落级别 keyword 匹配 + LLM 重排，不引入 Milvus/Chroma

**D6：Web UI——FastAPI 直接服务静态文件，零构建工具**
- 方案：`app/static/` 下放原生 HTML + CSS + JS，FastAPI 通过 `StaticFiles` 挂载。前端用原生 JS 调后端 API，不引 React/Vue 等框架
- 原因：MVP 的 UI 只需 3 个页面（上传+索引 / 阅读脱水版+Q&A / 查看全局上下文），React/Vue 的构建链和状态管理是过度设计
- 被拒方案：Gradio（样式定制能力弱，阅读长文本体验差）、React/Vite（MVP 引入构建工具链增加维护成本）

### 模块放置

本 feature 放在项目根目录，三模块各自为独立包：
- `app/modules/indexer/` —— 模块一（全局索引）
- `app/modules/dehydration/` —— 模块二（智能脱水）
- `app/modules/qa_assistant/` —— 模块三（伴随式 Q&A）

原因：三模块各自内聚、通过全局上下文数据交互，没有理由塞进同一个包。

### 前置依赖

无。MVP 从零构建。

### 主流程概述

```
用户上传 txt/epub
    → [模块一] 解析文本 → LLM 提取角色/主线/伏笔 → 存 context.json
    → [模块二] 逐章读取 + 加载 context → LLM 逐块判定三层 → 拼接脱水版 → 存 dehydrated.txt
    → 用户阅读脱水版 → [模块三] 用户提问 → 检索原版 + context → LLM 回答
```

---

## 第 2 节：接口契约

### 模块一：全局索引

**输入**：完整小说文本（txt 字符串）
**输出**：`GlobalContext`

#### 分析步骤（分三阶段）

```
原始文本
  → 阶段 A：章节解析 → chapters[]
  → 阶段 B：分批提取 → partial_contexts[]（每 10 章一组）
  → 阶段 C：合并去重 → GlobalContext（最终档案）
```

**阶段 A：章节解析**（纯代码，不调 LLM）
1. 用正则匹配章节标题：`^第[零一二三四五六七八九十百千万〇0-9]+[章节回卷]`
2. 按章节边界切分，得到 `chapters = [{"number": 1, "title": "觉醒", "text": "..."}, ...]`
3. 章节识别失败 → 降级为按固定字数切（每 3000 字一块，标记 `auto_split: true`）

**阶段 B：分批提取**（调 LLM，每批 ~10 章）
- 把 chapters 按每 10 章一组切分（可配置 `BATCH_SIZE=10`）
- 每组调一次 LLM，Prompt 要求输出 JSON：
  ```json
  {
    "characters": [{"name": "林风", "role": "主角", "relationships": ["..."], "chapters": [1,2,5]}],
    "plot": ["第1章：林风觉醒灵根", "第2章：拜入青云宗", ...],
    "foreshadows": [{"description": "神秘玉佩", "chapters": [5], "hints_resolved": false}],
    "key_items": ["青云剑", "神秘玉佩"]
  }
  ```
- 每批 LLM 输出后做 `PartialContext.model_validate()` 校验，失败 → retry（最多 2 次）

**阶段 C：合并去重**（纯代码，不调 LLM）
- `characters`：同名角色合并（name 完全匹配），取最早 first_chapter、最晚 last_chapter，relationships 去重合并
- `plot`：直接按章节号追加，天然有序
- `foreshadows`：同名伏笔合并，后续批次出现同伏笔时标记 `resolved = True`（说明已回收）
- `key_items`：去重合并
- 合并完成后做**最终收敛**：
  - 按角色出场章节数过滤：出场 < 3 章的非主角/配角角色 → 降级为"其他"
  - 全书角色 role 分布校验：必须至少 1 个主角，0-3 个配角

#### 类型定义

```python
# app/models/context.py
from pydantic import BaseModel
from typing import Optional

class PartialContext(BaseModel):
    """单批 LLM 提取结果"""
    characters: list[dict]
    plot: list[str]
    foreshadows: list[dict]
    key_items: list[str]

class CharacterProfile(BaseModel):
    name: str              # 角色名
    role: str              # 主角/配角/反派/其他
    relationships: list[str] = []   # 与其他角色的关系描述
    first_chapter: int     # 首次出场章节
    last_chapter: int      # 最后出场章节

class Foreshadow(BaseModel):
    description: str       # 伏笔内容摘要
    setup_chapter: int     # 埋下伏笔的章节
    resolved: bool = False  # 是否已回收

class GlobalContext(BaseModel):
    book_title: str
    total_chapters: int
    characters: list[CharacterProfile]
    main_plot: list[str]   # 主线剧情脉络，每章一条
    foreshadows: list[Foreshadow]
    key_items: list[str]   # 关键道具/设定

class IndexResponse(BaseModel):
    book_id: str
    context: GlobalContext
    status: str            # "completed" / "failed"
    error: Optional[str] = None
```

**示例**：
```
# 输入：某玄幻小说第 1-50 章文本
# LLM 处理后输出的 GlobalContext 片段：
{
  "book_title": "XX 修仙传",
  "total_chapters": 50,
  "characters": [
    {"name": "林风", "role": "主角", "relationships": ["师父：云中子"], "first_chapter": 1, "last_chapter": 50},
    {"name": "苏清雪", "role": "女主", "relationships": ["青梅竹马：林风"], "first_chapter": 3, "last_chapter": 48}
  ],
  "main_plot": ["第1章：林风觉醒灵根", "第2章：拜入青云宗", ...],
  "foreshadows": [
    {"description": "神秘玉佩来历不明", "setup_chapter": 5, "resolved": false}
  ],
  "key_items": ["青云剑", "神秘玉佩"]
}
```

### 模块二：智能切片脱水

**输入**：单章文本 + `GlobalContext`
**输出**：处理后的脱水文本

#### 脱水流程（每章独立）

```
章节原文
  → 按段落切分为 blocks（每块 500-800 字，按段落边界对齐）
  → 对每个 block 调 LLM 判定 layer（keep/summarize/delete）+ 输出处理后文本
  → 按原顺序拼接（DELETE 的块跳过不输出）
  → 输出脱水文本
```

#### 三层判定规则（LLM 判定依据）

**KEEP（保留原文，一字不改）**——满足任一：
- 核心角色（`GlobalContext.characters` 中 role=主角/配角的）之间的对话或互动
- 涉及主线关键转折、生死危机、情感走向、亲密场景
- 涉及伏笔（`GlobalContext.foreshadows`）或关键道具（`GlobalContext.key_items`）的情节

**SUMMARIZE（压缩为 `[注：XXX]` 格式）**——满足任一：
- 支线任务、打怪升级重复过程、获取非核心道具
- 非核心角色的戏份（角色不在 core_characters 中）
- 输出格式严格为：`[注：谁+做了什么+结果]`

**DELETE（直接剔除，输出中不出现）**——满足任一：
- 纯环境描写（无角色、不推动情节）
- 重复的武功招式说明
- 路人震惊反应、字数注水、重复前文内容

#### 判定 Prompt（`app/modules/dehydration/prompt.py`）

```
你是网文脱水编辑器。根据以下档案判定每个文本块的处理方式：

【核心角色】{core_characters}
【主线关键词】{main_plot_keywords}
【伏笔】{foreshadows}
【关键道具】{key_items}

判定规则：
→ KEEP（保留原文，一字不改）：核心角色对话/互动、主线转折、生死危机、情感场景、涉及伏笔/道具
→ SUMMARIZE（压缩为 [注：XXX]）：支线任务、升级重复过程、非核心角色戏份、非核心道具
→ DELETE（直接剔除）：纯环境描写、重复招式说明、路人震惊反应、字数注水

待处理文本：
{block_text}

只输出 JSON：
{"layer": "keep|summarize|delete", "output": "原文/摘要/空串"}
```

#### 类型定义

```python
# app/models/dehydration.py
from pydantic import BaseModel
from enum import Enum

class Layer(str, Enum):
    KEEP = "keep"
    SUMMARIZE = "summarize"
    DELETE = "delete"

class BlockResult(BaseModel):
    text: str
    layer: Layer
    output: str

class DehydrateRequest(BaseModel):
    book_id: str
    chapter_number: int
    chapter_text: str

class DehydrateResponse(BaseModel):
    book_id: str
    chapter_number: int
    blocks: list[BlockResult]
    dehydrated_text: str
```

**示例**：

原文（第15章片段，约 420 字）：
```
清晨，薄雾笼罩着七玄门后山。韩立独自站在瀑布旁，
手中把玩着那个神秘的小瓶。阳光透过水雾，折射出一道道彩虹。

"又是一天。"韩立叹了口气。他自从拜入七玄门以来，已经过去了整整三年。
这三年来，他每天都在努力修炼长生功，但进展缓慢。

突然，韩立感觉到一股强大的气息从远处逼近。一个身着黑袍的老者出现在他面前。
"你就是韩立？"老者冷冷地问道。
"正是。前辈是？"韩立警惕地后退一步。
"老夫大衍神君。你手中的瓶子，从何而来？"

与此同时，在山下的七玄门中，弟子们正在议论纷纷。
"听说了吗？张师兄又突破了！他已经达到了炼气六层！"
"是啊是啊，张师兄真是天才！"
"太厉害了！我们什么时候才能有他一半的实力啊！"
"真羡慕啊..."
```

脱水后（约 180 字 + 1 句摘要）：
```
"又是一天。"韩立叹了口气。他自从拜入七玄门以来，已经过去了整整三年。
这三年来，他每天都在努力修炼长生功，但进展缓慢。

突然，韩立感觉到一股强大的气息从远处逼近。一个身着黑袍的老者出现在他面前。
"你就是韩立？"老者冷冷地问道。"正是。前辈是？"韩立警惕地后退一步。
"老夫大衍神君。你手中的瓶子，从何而来？"韩立心中一惊。
这个瓶子的来历他从未告诉过任何人。

[注：七玄门张师兄突破至炼气六层，获赐玄铁剑]
```

判定明细：
- 第1段（环境描写，无角色）→ DELETE
- 第2段（韩立独白，核心角色）→ KEEP
- 第3段（大衍神君登场，核心角色+伏笔）→ KEEP
- 第4段（路人弟子议论，非核心角色+废话）→ SUMMARIZE

### 模块三：伴随式 Q&A

**输入**：用户问题 + `book_id`
**输出**：回答

```python
# app/models/qa.py
from pydantic import BaseModel

class AskRequest(BaseModel):
    book_id: str
    question: str

class AskResponse(BaseModel):
    answer: str
    source_chapters: list[int]  # 回答参考了哪些章节
```

**示例**：
```
# 输入：
{"book_id": "abc123", "question": "神秘玉佩到底是谁给的？"}

# 内部流程：
# 1. 从 GlobalContext 查伏笔库：玉佩在第5章出现，未回收
# 2. 检索原版第5章及前后章节相关段落
# 3. LLM 基于检索内容生成回答

# 输出：
{
  "answer": "神秘玉佩是林风在第5章于后山山洞中偶然发现的，
             当时玉佩上刻有模糊的古文，但书中尚未交代来历。
             这可能是一个伏笔。",
  "source_chapters": [5, 6, 12]
}
```

### Web 页面

| 路径 | 页面 | 关键交互 |
|---|---|---|
| `/` | 首页（上传+索引） | 文件上传 → 触发索引 → 显示进度 → 索引完成显示角色/主线/伏笔概览 |
| `/read` | 阅读器（脱水版+Q&A） | 左侧脱水版全文滚动 + 右侧 Q&A 侧栏（输入问题 → 显示回答 + 引用章节） |
| `/context` | 全局上下文查看页 | 展示角色清单（可筛选）/ 主线脉络（时间线）/ 伏笔库（已回收/未回收） |

### API 路由总览

| 方法 | 路径 | 功能 | 请求体 | 响应体 |
|---|---|---|---|---|
| POST | `/api/books/upload` | 上传小说 | `multipart/form-data` | `book_id` |
| POST | `/api/index/{book_id}` | 触发全局索引 | 无 | `IndexResponse` |
| GET | `/api/index/{book_id}/context` | 获取全局上下文 | 无 | `GlobalContext` |
| POST | `/api/dehydrate/{book_id}` | 触发全书脱水 | 无 | `{"status": "completed"}` |
| GET | `/api/dehydrate/{book_id}/progress` | 查询脱水进度（SSE） | 无 | `{"chapter": N, "total": M, "status": "running"}` |
| GET | `/api/dehydrate/{book_id}/output` | 获取脱水版全文 | 无 | `{"text": "..."}` |
| POST | `/api/qa/ask` | Q&A 提问 | `AskRequest` | `AskResponse` |
| GET | `/api/books/{book_id}/status` | 查询书籍处理状态 | 无 | `{"indexed": bool, "dehydrated": bool}` |

---

## 第 3 节：实现提示

### 改动计划

| # | 步骤 | 文件操作 | 说明 |
|---|---|---|---|
| 1 | 项目骨架 | 新建 `pyproject.toml`, `app/__init__.py`, `app/main.py` | FastAPI 项目结构 |
| 2 | 数据模型 | 新建 `app/models/context.py`, `app/models/dehydration.py`, `app/models/qa.py` | Pydantic 模型 |
| 3 | 存储层 | 新建 `app/storage.py` | 文件读写 + SQLite book 元数据 |
| 4 | LLM 客户端 | 新建 `app/llm_client.py` | 统一 LLM 调用接口（OpenAI 兼容协议） |
| 5 | 模块一（索引） | 新建 `app/modules/indexer/chapter_parser.py`, `app/modules/indexer/extractor.py`, `app/modules/indexer/merger.py`, `app/modules/indexer/prompt.py`, `app/modules/indexer/service.py` | 章节解析 + 分批提取 + 合并去重 三阶段 |
| 6 | 模块二（脱水） | 新建 `app/modules/dehydration/service.py`, `app/modules/dehydration/prompt.py` | 切片脱水逻辑 |
| 7 | 模块三（Q&A） | 新建 `app/modules/qa_assistant/service.py` | 检索 + 回答 |
| 8 | 路由层 | 新建 `app/routes/index.py`, `app/routes/dehydrate.py`, `app/routes/qa.py`, `app/routes/books.py`, `app/routes/web.py` | API 端点 + 静态文件服务 |
| 9 | Web UI | 新建 `app/static/index.html`, `app/static/read.html`, `app/static/context.html`, `app/static/app.css`, `app/static/app.js` | 3 个页面 + 公共样式/逻辑 |
| 10 | 入口 + 配置 | 新建 `app/config.py`, `.env.example` | 启动入口 |

### 实现风险

| 风险 | 应对 |
|---|---|
| 单章 > 15000 字超出 LLM context window | 按段落二次切分（每块 ≤ 8000 字符），逐块处理后拼接 |
| LLM 脱水判定不稳定（同一块两次判定结果不同） | 加入 retry 逻辑：同一块最多重试 1 次，取第一次结果 |
| 全局索引时 LLM 输出格式不合规 | Pydantic `model_validate()` 严格校验 + retry（最多 2 次） |
| Q&A 检索命中率为空 | 降级策略：检索无结果时，直接用全局上下文 + 整书摘要回答 |
| 章节解析失败（非标准标题格式） | 降级为按固定字数切分（每 3000 字一块），标记 `auto_split: true` 让下游感知上下文可能不完整 |
| 同名角色不同写法（"林风"/"风哥"/"那少年"） | MVP 阶段不做别名合并，依赖 LLM 在提取时统一用本名。极端情况靠用户手动修正 |

### 推进顺序

1. **项目骨架 + 数据模型**（步骤 1-2）→ 验证：`python -c "from app.models.context import GlobalContext; print('OK')"`
2. **存储层 + LLM 客户端**（步骤 3-4）→ 验证：`python -c "from app.storage import Storage; s = Storage('/tmp/test'); s.save_book('test', 'hello'); print(s.load_book('test'))"`
3. **模块一（索引）——阶段 A 章节解析**（步骤 5a）→ 验证：给一段带 10 章标题的文本 → chapters 长度=10，标题和正文正确分离
4. **模块一（索引）——阶段 B 分批提取 + 阶段 C 合并**（步骤 5b）→ 验证：给一段 5000 字测试文本（模拟 2 批），能输出合法的 `GlobalContext`，同名角色合并为 1 条
4. **模块二（脱水）**（步骤 6）→ 验证：给一章测试文本 + mock context，输出脱水文本且三种 layer 均有体现
5. **模块三（Q&A）**（步骤 7）→ 验证：对已有索引的书提问，回答能引用正确章节
6. **路由层**（步骤 8）→ 验证：`uvicorn app.main:app --reload` 启动后，curl 所有 API 端点均返回预期结果
7. **Web UI**（步骤 9）→ 验证：浏览器打开 `/` 能上传文件，`/read` 能显示脱水文本，`/context` 能展示上下文

### 测试设计

**T1：全局索引格式校验**
- 约束：LLM 输出必须能被 `PartialContext.model_validate()` 解析
- 验证：mock LLM 返回非法 JSON → 应触发 retry 并返回友好错误

**T1b：章节解析正确性**
- 约束：标准章节标题（第1章、第二回、第100章）必须正确识别
- 验证：输入带 10 章标题的文本 → chapters 长度 = 10，标题和正文正确分离

**T1c：合并去重逻辑**
- 约束：同名角色在 3 批中均出现 → 合并为 1 条，first/last 正确
- 验证：构造 3 批 partial contexts，同名角色 → 最终 characters 只有 1 条

**T2：脱水三层分类正确性**
- 约束：同一段文本，给定相同 context，脱水结果稳定
- 验证：用同一段包含对话+景色+支线的情节输入，检查三层分类

**T3：摘要格式固定**
- 约束：摘要层输出必须以 `[注：` 开头、`]` 结尾
- 验证：检查所有 summarize 层的 output 字段格式

**T4：Q&A 不基于脱水版回答**
- 约束：回答必须引用原版内容，而非脱水版
- 验证：提问一个只在原版出现但被脱水删除的细节 → 回答应能命中

**T5：大章（> 15000 字）处理**
- 约束：超长章节不会报错或截断
- 验证：输入 20000 字章节 → 完整输出脱水结果

---

## 第 4 节：与项目级架构文档的关系

本项目为从零构建，当前 `codestable/architecture/` 下无文档。

本 feature 完成后，需在架构中心创建以下文档：

1. **`codestable/architecture/ARCHITECTURE.md`**（架构总入口）
   - 归并本项目的三模块结构、数据流向（索引 → 脱水 → Q&A）
   - 归并 `GlobalContext` 作为核心数据实体
   - 归并 LLM 调用约束（OpenAI 兼容协议、retry 策略）
   - 归并 Web UI 三层页面结构（上传索引 / 阅读+Q&A / 上下文查看）

2. **`codestable/architecture/AGENTS.md`**（Agent 规约）
   - 记录三模块的文件组织约定（`app/modules/{module}/`）
   - 记录存储约定（`data/{book_id}/` 目录结构）
   - 记录前端文件约定（`app/static/` 原生 HTML，无构建链）

目前无历史架构文档需要更新。本 feature 的 design 即为架构起点。
