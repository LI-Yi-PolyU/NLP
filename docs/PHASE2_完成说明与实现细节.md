# StoryWeaver Phase 2 完成说明与实现细节

## 1. 结论

Phase 2 已完成，已实现规格书要求的核心链路：
- NLU（本地意图识别 + API fallback）
- State（SQLite状态管理）
- Consistency（三层一致性检测）
- 主协调器（最小可运行的端到端流程）

当前代码已可执行单轮处理：输入玩家指令 -> 输出结构化结果并更新状态。

---

## 2. 按规格书对应的实现项

### 2.1 本地 NLU 模块

文件：`src/nlu/local_bert.py`

实现内容：
- `LocalIntentClassifier` 类
- 读取 `config/model_config.yaml` 中本地模型配置
- 意图标签映射：`EXPLORE, NEGOTIATE, ATTACK, USE_ITEM, ASK_INFO`
- `predict(text)` 返回：
  - `intent`
  - `confidence`
  - `entities`
  - `source`（用于调试来源）
- `_extract_entities` 调用规则实体抽取

工程增强：
- 若本地模型不可加载，自动回退到关键词分类，保证不中断。
- 若模型置信度很低，使用关键词结果进行矫正（避免未微调分类头直接误判）。

### 2.2 实体抽取模块

文件：`src/nlu/entity_extractor.py`

实现内容：
- 基于 `config/world_setting.yaml` 中的地点、角色、物品（id + name）做字符串匹配
- 输出统一实体结构：
  - `type`
  - `value`
  - `start`
  - `end`
- 长词优先匹配，减少短词覆盖导致的 span 错误

### 2.3 API Fallback 模块

文件：`src/nlu/api_fallback.py`

实现内容：
- `APIIntentFallback` 类
- 当本地 NLU 置信度低于阈值（默认 0.7）时触发
- 调用 DeepSeek 兼容接口，要求 JSON 输出
- 返回结构与本地 NLU 对齐，并补充 `source="api_fallback"`

环境变量：
- 读取 `DEEP_SEEK_API_KEY`

### 2.4 状态管理器（关键模块）

文件：`src/core/state_manager.py`

实现内容：
- `Fact` 数据类：`subject/predicate/object/turn/valid`
- SQLite 表自动初始化（`facts`）
- `get_current_state(subject=None)`：返回当前有效状态快照
- `update_state(facts)`：批量写入事实，对单值属性执行覆盖失效
- `check_fact_exists(subject, predicate, object)`：有效事实查询

工程增强：
- 首次启动自动灌入世界初始状态（player位置、角色状态、物品位置）

### 2.5 三层一致性检查器

文件：`src/core/consistency_checker.py`

实现内容：
- `ConsistencyChecker.verify(proposed_facts)` 返回：
  - `passed`
  - `violations`
  - `can_auto_fix`
  - `fixed_facts`

三层检查：
1. Hard Rules：
- `dead_character_cannot_speak`
- `item_not_held_cannot_be_used`
- `location_not_connected_cannot_travel`

2. DB Check：
- 状态冲突检测（例如死亡状态不可回退）

3. Semantic：
- 预留本地 NLI 推理入口（可用时启用）

自动修复：
- 对“未持有物品却使用”支持自动修复为安全动作

### 2.6 主协调器

文件：`src/core/game_engine.py`

实现内容：
- `GameEngine.process_turn(user_input)` 实现主链路：
  1) 本地意图识别
  2) 低置信度 API fallback
  3) 意图转事实
  4) 一致性验证
  5) 通过则更新状态；可修复则应用修复；否则拒绝更新
  6) 返回结构化结果（叙事、状态变更、下一步选项、一致性备注）

并暴露调试字段：
- `last_intent`
- `last_consistency_result`
- `last_retrieved_scenarios`

---

## 3. 与规格书的差异说明（透明披露）

1. 本地 BERT 现状
- 当前是“可推理但未微调”的状态，分类头会提示未训练。
- 为保证可用，已加入关键词回退/矫正策略。

2. 语义一致性层
- 已实现入口与调用框架；目前为轻量实现，避免 Phase 2 过重依赖。
- 语义冲突细粒度规则可在 Phase 3 前继续增强。

3. 生成模块
- Phase 2 目标是打通 NLU->State->Consistency 主链路。
- 复杂生成（RAG + Story API JSON Schema 强约束）在 Phase 3 继续完善。

---

## 4. 已完成验证

### 4.1 代码错误检查

以下文件均无静态错误：
- `src/nlu/local_bert.py`
- `src/nlu/api_fallback.py`
- `src/core/state_manager.py`
- `src/core/consistency_checker.py`
- `src/core/game_engine.py`

### 4.2 冒烟测试

执行逻辑：
- 实例化 `GameEngine`
- 输入：`我想去forest探索`
- 验证输出包含：
  - narration
  - state_changes
  - next_options
  - consistency 结果

结果：
- `has_narration = True`
- `has_state_changes = True`
- `has_next_options = True`
- `consistency_passed = True`

---

## 5. 如何使用 Phase 2

### 5.1 安装依赖

```bash
pip install -r requirements.txt
```

> 已新增 Phase 2 依赖：`transformers`, `torch`

### 5.2 配置 API Key（可选但推荐）

PowerShell：

```powershell
$env:DEEP_SEEK_API_KEY="your_key"
```

### 5.3 最小调用示例

```python
from src.core.game_engine import GameEngine

engine = GameEngine()
result = engine.process_turn("我想去cave看看")
print(result)
```

返回示例字段：
- `narration`
- `dialogue`
- `state_changes`
- `next_options`
- `consistency_notes`

---

## 6. 文件总览（Phase 2新增/实现）

- `src/nlu/entity_extractor.py`
- `src/nlu/local_bert.py`
- `src/nlu/api_fallback.py`
- `src/core/state_manager.py`
- `src/core/consistency_checker.py`
- `src/core/game_engine.py`
- `requirements.txt`（新增 Phase 2 依赖）

---

## 7. 下一步建议（进入 Phase 3）

1. 实现 `src/generation/retriever.py`（向量索引构建 + 检索）
2. 实现 `src/generation/story_gen.py`（JSON Schema 强约束生成）
3. 接入 `src/evaluation/auto_eval.py` 做端到端评估
4. 补充 `run_evaluation.py` 一键评估入口

这样可形成可演示、可评估、可复现实验闭环。
