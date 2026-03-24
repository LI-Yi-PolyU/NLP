# StoryWeaver 完整技术规格书（当前实现对齐版）
**版本**：2026-03-24 对齐当前代码库  
**目标**：构建 AI 文本冒险游戏，支持动态剧情生成、状态一致性维护、自动化评估与演示证据导出  
**技术约束**：单人开发、4 周交付、混合架构（本地 NLP + API 生成）  
**评分目标**：14.5/15（课程顶级档）

---

## 一、当前项目结构（与现代码一致）

```text
nlp-project/
├── config/
│   ├── world_setting.yaml
│   ├── model_config.yaml
│   ├── entity_aliases.yaml
│   └── prompts/
│       ├── intent_classification.txt
│       ├── story_generation.json
│       └── consistency_rules.yaml
├── data/
│   ├── raw_corpus/
│   │   └── synthetic_scenarios.jsonl
│   ├── benchmarks/
│   │   ├── intent_train.jsonl
│   │   ├── intent_test.jsonl
│   │   ├── consistency_test.jsonl
│   │   ├── demo_scenarios.json
│   │   ├── demo_trace.jsonl
│   │   ├── exported_trace.json
│   │   └── day3_evidence.json
│   └── vector_index/
│       ├── narrative.index
│       ├── narrative_vectors.npy
│       └── narrative_meta.json
├── src/
│   ├── data_validator.py
│   ├── nlu/
│   │   ├── local_bert.py
│   │   ├── api_fallback.py
│   │   └── entity_extractor.py
│   ├── core/
│   │   ├── state_manager.py
│   │   ├── consistency_checker.py
│   │   └── game_engine.py
│   ├── generation/
│   │   ├── retriever.py
│   │   └── story_gen.py
│   ├── evaluation/
│   │   ├── metrics.py
│   │   └── auto_eval.py
│   └── demo/
│       ├── visualizer.py
│       └── demo_controller.py
├── app.py
├── run_data_pipeline.py
├── run_evaluation.py
├── run_day3_evidence.py
├── evaluation_report.json
├── DAY3_答辩证据包.md
└── README.md
```

---

## 二、系统目标与当前能力

### 2.1 系统目标
1. 识别玩家输入意图并提取实体。
2. 将意图映射为状态变化，执行一致性校验。
3. 生成结构化剧情输出（叙事、选项、状态备注）。
4. 支持多轮交互、主线推进、可解释调试信息。
5. 提供可复现实验与证据导出（评测报告 + trace）。

### 2.2 当前已实现能力
1. 本地 NLU：可训练轻量分类分支 + BERT/关键词回退。
2. 三层一致性：硬规则、状态库冲突、语义冲突判定。
3. 状态持久化：SQLite 事实库，支持回合更新与快照。
4. 叙事生成：RAG 检索 + API 结构化输出 + 后处理。
5. 演示模式：LIVE / SCRIPTED 双模式，支持 trace 导出。
6. 评测体系：意图、一致性、端到端延迟、分支多样性。
7. Day3 证据包：自动聚合评测与演示证据并生成 Markdown。

---

## 三、核心配置（当前实际值）

### 3.1 世界观配置（config/world_setting.yaml）
1. 场景：village、forest、cave，均已定义连接关系。
2. 角色：elder、hunter，包含 location/status/friendly_to_player。
3. 物品：sword、torch，包含 location 与 holder。
4. 硬规则：
   - dead_character_cannot_speak
   - item_not_held_cannot_be_used
   - location_not_connected_cannot_travel

### 3.2 模型配置（config/model_config.yaml）
1. API：base_url 为 DeepSeek，model_nlu_fallback/model_generation 为 deepseek-chat。
2. 本地模型：
   - bert_model: bert-base-chinese
   - nli_model: uer/roberta-base-chinese_nli
   - embedding_model: shibing624/text2vec-base-chinese

---

## 四、端到端流程（当前实现）

### 4.1 离线数据与索引流程
入口：run_data_pipeline.py

流程：
1. generate_intent_dataset(n_train=500, n_test=100)
   - 依据世界观实体生成意图样本。
   - 默认含 10% UNKNOWN 噪声样本。
2. generate_consistency_benchmark(n_pairs=200)
   - 基于硬规则生成 50% 一致 + 50% 冲突样本。
3. build_rag_corpus(output_dir=data/raw_corpus)
   - 目标 300 条语料。
   - 若有 API key 尝试先生成约 60 条高质量片段，其余模板补齐。
4. _build_demo_scenarios()
   - 生成演示缓存路径（safe/risky/tradeoff）。

### 4.2 在线交互流程
入口：app.py -> DemoController -> GameEngine

每轮处理：
1. LocalIntentClassifier 识别意图与实体。
2. 低置信时触发 APIIntentFallback（若 key 存在）。
3. 意图转事实 proposed_facts。
4. ConsistencyChecker 校验：
   - 硬规则
   - 状态库冲突
   - 语义冲突
5. 合法则更新状态；可修复冲突则自动修复；不可修复则拒绝并给出说明。
6. StoryGenerator（可用时）生成结构化剧情并回写 state_changes。
7. GameEngine 注入主线推进建议、终局判定与回合控制。
8. app.py 进行流式输出与调试面板更新。

---

## 五、模块规格（按当前代码）

### 5.1 NLU 模块（src/nlu）
1. local_bert.py
   - 先走线性分类器（TF-IDF + LogisticRegression，训练集来自 data/benchmarks/intent_train.jsonl）。
   - 线性低置信再走本地 BERT 分支；BERT 不稳定时关键词修正。
   - 关键词无命中时返回 UNKNOWN。
2. api_fallback.py
   - 仅在 DEEP_SEEK_API_KEY 存在且本地低置信时启用。
   - 输出 intent/entities/confidence/source。
3. entity_extractor.py
   - 基于规则和世界观实体别名抽取。

### 5.2 状态与一致性模块（src/core）
1. state_manager.py
   - SQLite facts 表：subject/predicate/object/turn/valid/timestamp。
   - 支持世界初始状态引导写入。
   - get_current_state/update_state/check_fact_exists 已实现。
2. consistency_checker.py
   - verify 返回 passed/violations/can_auto_fix/fixed_facts。
   - 已实现三层逻辑与语义冲突判定接口。
   - 自动修复覆盖“未持有物品却使用”等高频冲突。
3. game_engine.py
   - 全流程编排、主线阶段建议、结局判定。
   - 支持 state_changes 的 dict/list 兼容与 add 增量更新。
   - 支持背包脏数据清洗与展示友好化。

### 5.3 生成与检索模块（src/generation）
1. retriever.py
   - 使用向量模型编码文本。
   - 优先 FAISS 检索，缺失时回退 numpy 相似度。
2. story_gen.py
   - 生成输出目标为结构化 JSON。
   - 优先 json_schema，接口不支持时回退 json_object。
   - 后处理：
     - 规范 next_options/consistency_notes
     - 兜底中文输出
     - 调用一致性复检并提示修正。

### 5.4 评测与演示模块（src/evaluation, src/demo）
1. auto_eval.py
   - _eval_intent：意图分类指标 + 错误样例。
   - _eval_consistency：一致性检测指标 + 错误样例。
   - _eval_latency：端到端 GameEngine 延迟（mode=end_to_end_game_engine）。
   - _eval_diversity：生成多样性，API不可用时使用本地回退文本。
2. demo_controller.py
   - LIVE 与 SCRIPTED 双模式。
   - 支持 debug_view 与 trace 导出。
3. run_day3_evidence.py
   - 汇总 evaluation_report + trace，输出：
     - data/benchmarks/day3_evidence.json
     - DAY3_答辩证据包.md

---

## 六、关键数据格式（当前约束）

### 6.1 意图数据（intent_train/intent_test）
字段：
1. text
2. intent
3. entities（含 type/value/start/end）
4. confidence_score
5. metadata

### 6.2 一致性测试数据（consistency_test）
字段：
1. facts
2. label
3. expected_label
4. rule_type
5. rule_violated

### 6.3 游戏轮次输出（运行时）
核心字段：
1. narration
2. dialogue（可选）
3. state_changes
4. next_options
5. consistency_notes
6. rag_sources

扩展字段（终局时）：
1. game_over
2. ending_type
3. final_state

---

## 七、当前评测结果（evaluation_report.json）

最新结果（本地可复现）：
1. intent_recognition
   - accuracy: 1.0
   - f1_macro: 1.0
2. consistency_detection
   - accuracy: 1.0
   - f1_macro: 1.0
3. generation_latency
   - mode: end_to_end_game_engine
   - rounds: 12
   - avg_ms: 8.68
4. branch_diversity
   - sample_count: 5
   - diversity_score: 1.0

说明：
1. 当前结果在同分布数据上偏高，已在 Day3 文档中标注“彩排口径”。
2. 若启用 API key，分支多样性将更多反映线上生成波动。

---

## 八、演示与答辩材料映射

### 8.1 可直接用于演示
1. app.py 实时界面（含流式输出）。
2. DemoController SCRIPTED 模式（关键路径保底）。
3. 导出 trace（exported_trace.json）。

### 8.2 可直接用于报告
1. evaluation_report.json（指标）。
2. day3_evidence.json（证据聚合）。
3. DAY3_答辩证据包.md（摘要化可讲稿）。
4. DAY3_评分对齐说明.md（按评分标准映射）。

---

## 九、与原版规格的差异说明（已对齐方向）

1. 原版将 local_bert 作为单一主分支；当前实现加入线性分类分支以提升稳定性与可复现精度。
2. 原版延迟评测描述偏泛；当前实现明确为端到端 GameEngine 口径。
3. 原版更强调一次性 API 生成语料；当前实现为“API优先 + 模板补齐”的稳态流程。
4. 原版以计划型模板为主；当前文档为“代码现状快照”，可直接对照仓库执行。

---

## 十、运行命令（当前有效）

1. 数据流水线：
   - python run_data_pipeline.py
2. 自动评测：
   - python run_evaluation.py
3. 证据导出：
   - python run_day3_evidence.py
4. 启动服务：
   - python app.py

环境说明：
1. 配置 DEEP_SEEK_API_KEY 时可启用 API fallback 与 API 生成分支。
2. 未配置 key 时，系统自动回退本地可运行路径。
