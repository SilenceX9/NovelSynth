# AI 网文脱水机

## 项目目标

将长篇网文精简为"主线保留+支线摘要"的纯净版，去除注水废话，同时提供伴随式智能问答助手。

## 开发规范

- 使用 CodeStable 工作流管理 feature 生命周期
- 所有 feature 在 `codestable/feature/` 下建目录
- 需求档案在 `codestable/requirements/` 下
- 架构文档在 `codestable/architecture/` 下
- 遵循 `codestable/reference/shared-conventions.md` 的命名和结构约定

## 技术栈

- **后端**：Python 3.14 + FastAPI（async）
- **LLM**：OpenAI 兼容协议（`LLMClient` 统一封装，支持自定义 base_url / model）
- **存储**：SQLite（元数据）+ 文件系统（`data/{book_id}/`）
- **前端**：原生 HTML + CSS + JS，无构建链，FastAPI StaticFiles 提供
- **依赖**：httpx（LLM 调用）、aiosqlite（异步 SQLite）、pydantic / pydantic-settings

## 架构文档

详见 `codestable/architecture/ARCHITECTURE.md`（系统架构）和 `codestable/architecture/AGENTS.md`（Agent 开发约定）。
