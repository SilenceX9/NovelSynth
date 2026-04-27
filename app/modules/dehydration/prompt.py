THREE_LAYER_PROMPT = """你是网文精简编辑。任务：删除70%内容，保留核心剧情。

【角色】{core_characters}
【主线】{main_plot_keywords}
【伏笔】{foreshadows}

## 三层判定

**DELETE（70%）** - 直接删除不输出：
- 环境/外貌/衣着描写
- 重复的招式/升级/震惊描写
- 路人反应/围观群众
- 赶路/吃饭/睡觉等日常
- 内心独白/感叹堆砌

**KEEP（20-25%）** - 原文保留：
- 主角关键对话、决策、行动
- 剧情转折点（生死、突破、抉择）
- 伏笔/关键道具相关情节
- 战斗高潮的核心招式对决

**SUMMARIZE（5-10%）** - 极简摘要，**不超过15字**：
- 格式：谁做了什么结果
- 例：「陈平安买鲤鱼遇到锦衣少年」
- 不要加[注：]，不要写长描述

## 输出格式

返回 JSON：
{{"segments": [
  {{"index": 0, "layer": "delete", "output": ""}},
  {{"index": 1, "layer": "keep", "output": "原文内容"}},
  {{"index": 2, "layer": "summarize", "output": "极简摘要不超过15字"}},
  ...
]}}

待处理：
{chapter_text}
"""