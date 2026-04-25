# 共享路径与命名约定

## 0. 目录结构与命名

```
codestable/
├── architecture/          # 架构中心文档
│   └── *.md
├── feature/               # feature 目录，每个子目录一个 feature
│   └── {slug}/
│       ├── {slug}-design.md
│       ├── {slug}-checklist.yaml
│       └── {slug}-acceptance.md
├── reference/             # 共享参考（规约、术语等）
│   └── shared-conventions.md  ← 本文件
├── roadmap/               # 路线图
│   └── {roadmap}/
│       ├── {roadmap}-roadmap.md
│       └── {roadmap}-items.yaml
├── compound/              # 复合文档（learning 等）
└── requirements/          # 需求档案
    └── req-{slug}.md
```

**Slug 命名**：全小写，短横线分隔，如 `novel-dehydrator-mvp`。

**Feature 目录**：`codestable/feature/{slug}/`，所有 feature 产物聚合在此。

**Requirement 档案**：`codestable/requirements/req-{slug}.md`。

**Acceptance 报告**：`codestable/feature/{slug}/{slug}-acceptance.md`。

## 1. Design Doc Frontmatter 标准

```yaml
---
doc_type: feature-design
feature: {slug}
status: draft|approved
summary: 一句话概述
tags: [tag1, tag2]
requirement: req-{slug}  # 可为空，验收阶段回填
roadmap: {roadmap-slug}   # 可为空
roadmap_item: {item-slug} # 可为空
---
```

## 2. Checklist 标准

```yaml
feature: {slug}
steps:
  - name: 步骤名
    status: done|pending
checks:
  - name: 检查项
    status: pending|passed|failed
```

## 2.5. 衔接协议

- Design 阶段：`status` 从 `draft` → `approved`，生成 checklist
- Implement 阶段：逐个完成 checklist steps，status → `done`
- Accept 阶段：逐个验证 checklist checks，status → `passed`，产出 acceptance.md
- Requirement 回填：如果 `requirement` frontmatter 为空且新增能力，触发 cs-req backfill
- Roadmap 回写：如果 `roadmap`/`roadmap_item` 有值，更新 items.yaml status → `done`

## 3. 收尾推荐顺序

1. cs-learn（沉淀坑点/经验）
2. cs-decide（归档长期决定）
3. cs-guide（更新指南）
4. cs-libdoc（更新 API 文档）
5. scoped-commit（提交代码+文档）

## 4. Scoped-Commit 规则

验收阶段的 commit 包含：功能代码 + 方案 doc + 验收报告 + 更新的架构 doc + 更新的 requirement doc + 更新的 roadmap 文件。
Commit message 格式：`feat({slug}): {brief description}`
