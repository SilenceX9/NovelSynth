---
doc_type: learning
track: knowledge
date: 2026-04-25
slug: novel-dehydrator-text-processing-patterns
component: text-extraction / llm-pipeline
tags: [novel, text-parsing, llm-extraction, chunking, dedup]
---

# 小说脱水：长文本处理三个可复用模式

## 1. 章节解析正则 + 降级策略

**背景**

网文/小说章节标题格式相对统一但存在变体，需要一套能覆盖大多数场景的识别规则，并在识别失败时不崩溃而是优雅降级。

**指导原则**

- 主规则用正则 `^第[零一二三四五六七八九十百千万〇0-9]+[章节回卷]` 匹配章节标题
- 正则覆盖中文数字（零到万）、阿拉伯数字、混合写法
- 识别失败不报错，自动降级为每 3000 字切块
- 降级后每块头部标注 `[疑似第X章（切块）]` 保持下游一致性

**为什么重要**

小说文件的章节格式千差万别——有的用"第一章"、有的用"Chapter 1"、有的甚至没有章节标记。如果只依赖完美解析，遇到非常规文件就会整个流程断掉。降级策略保证任何输入都能走完流水线，只是精度不同。

**何时适用**

- 任何需要解析网文/小说/长篇小说文本的场景
- 章节标题格式不完全可控的批量处理
- 需要兼容用户自行上传文本的场景

**示例代码**

```python
import re

CHAPTER_PATTERN = re.compile(r'^第[零一二三四五六七八九十百千万〇0-9]+[章节回卷]')

def parse_chapters(text: str) -> list[tuple[str, str]]:
    """返回 [(chapter_title, chapter_content), ...]"""
    lines = text.split('\n')
    chapters = []
    current_title = None
    current_lines = []

    for line in lines:
        if CHAPTER_PATTERN.match(line):
            if current_title:
                chapters.append((current_title, '\n'.join(current_lines).strip()))
            current_title = line.strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_title:
        chapters.append((current_title, '\n'.join(current_lines).strip()))

    # 降级：一个章节都没识别到，按 3000 字切块
    if not chapters:
        return fallback_chunk(text, chunk_size=3000)

    return chapters


def fallback_chunk(text: str, chunk_size: int = 3000) -> list[tuple[str, str]]:
    """降级策略：按固定字数切块"""
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        idx = i // chunk_size + 1
        chapters.append((f'[疑似第{idx}章（切块）]', chunk))
    return chunks
```

## 2. 分批 LLM 提取 + 合并去重

**背景**

几十万字的小说不可能一次塞给 LLM。需要切分后分批提取实体（角色、伏笔等），最后合并结果。

**指导原则**

- 按每 10 章为一组调用 LLM 提取
- 合并阶段同名角色合并，取最早出现的 chapter 作为 first_appearance、最晚出现的作为 last_appearance
- 同名伏笔出现两次标记为 resolved（暗示出现 >= 2 次 = 已回收）
- 不同批次提取的结构统一为 `{name, description, chapter, type}` 再归并

**为什么重要**

这是处理超长文本的标准范式：分而治之 + 归并。单次 LLM 调用有 token 上限（通常 128K），且长上下文下注意力衰减会导致靠后的信息丢失。分批保证每段都在 LLM 的最佳上下文窗口内处理。

**何时适用**

- 任何超过 LLM 单次 token 上限的长文本信息提取
- 角色追踪 / 伏笔追踪 / 时间线提取
- 需要跨章节聚合信息的分析任务

**示例代码**

```python
from collections import defaultdict


def merge_characters(extractions: list[dict]) -> list[dict]:
    """合并分批提取的角色，取 first/last chapter 极值"""
    by_name = defaultdict(lambda: {
        'name': '',
        'first_appearance': float('inf'),
        'last_appearance': 0,
        'description': '',
    })

    for ext in extractions:
        for char in ext.get('characters', []):
            name = char['name']
            entry = by_name[name]
            entry['name'] = name
            entry['first_appearance'] = min(entry['first_appearance'], char.get('chapter', 0))
            entry['last_appearance'] = max(entry['last_appearance'], char.get('chapter', 0))
            # 保留最完整的描述
            if len(char.get('description', '')) > len(entry['description']):
                entry['description'] = char['description']

    return list(by_name.values())


def merge_foreshadowings(extractions: list[dict]) -> list[dict]:
    """合并伏笔：同名出现 >= 2 次标记 resolved"""
    by_name = defaultdict(lambda: {
        'name': '',
        'count': 0,
        'chapters': [],
        'description': '',
        'resolved': False,
    })

    for ext in extractions:
        for fw in ext.get('foreshadowings', []):
            name = fw['name']
            entry = by_name[name]
            entry['name'] = name
            entry['count'] += 1
            entry['chapters'].append(fw.get('chapter', 0))
            if len(fw.get('description', '')) > len(entry['description']):
                entry['description'] = fw['description']

    for entry in by_name.values():
        entry['resolved'] = entry['count'] >= 2

    return list(by_name.values())
```

## 3. 块级脱水判定

**背景**

给 LLM 做脱水（keep / summarize / delete）时，把整章丢给 LLM 效果差——LLM 倾向于全保留。将章按段落切成 500-800 字块，逐块判定，效果显著提升。

**指导原则**

- 以段落为自然切分点，每块 500-800 字（不切断段落中间）
- 对每块独立调用 LLM 判定 `keep | summarize | delete`
- DELETE 的块直接跳过，不拼接
- SUMMARIZE 的块用 LLM 生成一句话摘要后拼接
- KEEP 的块原文保留

**为什么重要**

块级判定比整章判定效果好得多，原因有三：

1. **粒度更精确**：一章里可能有核心对话 + 大量环境描写，整章判定要么全留要么全删，块级可以精细取舍
2. **降低 LLM 偏差**：上下文越短，LLM 越不容易"舍不得删"
3. **减少 token 浪费**：被标记 DELETE 的块不需要走 summarize 步骤

**何时适用**

- 任何长文本精简/摘要/脱水场景
- 文本中存在信息密度不均的段落（对话密集、描写稀疏交替）
- 需要在保留关键情节和压缩体积之间做平衡

**示例代码**

```python
def chunk_by_paragraphs(text: str, min_size: int = 500, max_size: int = 800) -> list[str]:
    """按段落切块，不切断段落中间"""
    paragraphs = text.split('\n\n')
    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len > max_size and current:
            chunks.append('\n\n'.join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append('\n\n'.join(current))

    return chunks


def dehydrate_chunks(chunks: list[str]) -> str:
    """逐块脱水后拼接"""
    result = []
    for chunk in chunks:
        decision = llm_decide(chunk)  # keep | summarize | delete
        if decision == 'keep':
            result.append(chunk)
        elif decision == 'summarize':
            result.append(llm_summarize(chunk))
        # delete 的块直接跳过
    return '\n\n'.join(result)
```

## 下次会做什么不同的事

1. **章节解析扩展多语言正则**：当前正则只覆盖中文写法。下次应补充 `^(Chapter|CHAPTER|ch\.?)\s*\d+` 等英文模式，用 OR 组合匹配。
2. **分批大小动态调整**：10 章一组是经验值。下次可以根据章节字数动态计算组大小——平均每章 3000 字就 10 章一组，5000 字就 6 章一组，保证每组不超 LLM 上限。
3. **块级判定加缓存**：同一章如果被脱水两次（比如不同脱水参数），块级结果可以缓存。下次应加 chunk-level cache key（章节 hash + 块序号），避免重复调 LLM。
4. **合并去重加模糊匹配**：当前同名才合并。但"张三"和"张三（少年时）"、"老张"实际是同一个人。下次应接入简单的字符串相似度（如 Levenshtein）或让 LLM 做一次别名对齐。
