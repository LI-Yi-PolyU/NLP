# StoryWeaver Phase 3 完成说明与使用指南

## 1. 完成结论

Phase 3（生成与评估）已完成，已实现：
- RAG 检索器
- API 故事生成器
- 自动化评估器
- 一键评估入口

并已验证 `run_evaluation.py` 可执行并产出 `evaluation_report.json`。

---

## 2. 对照规格书的实现内容

### 2.1 RAG 检索器

文件：`src/generation/retriever.py`

实现要点：
- `NarrativeRetriever` 类
- 自动加载 `data/raw_corpus/*.jsonl` 语料
- 优先使用 `sentence-transformers` 生成向量
- 优先使用 FAISS (`faiss-cpu`) 建立向量索引
- 若 FAISS 或 embedding 模型不可用，自动回退到哈希向量检索
- `retrieve(query, current_location, k=3)` 返回：
  - `id`
  - `scenario`
  - `plot_summary`
  - `similarity`

增强点：
- 对当前地点一致的文档增加检索加权，提升场景相关性。

### 2.2 API 故事生成器

文件：`src/generation/story_gen.py`

实现要点：
- `StoryGenerator` 类
- 集成 RAG 检索结果作为 few-shot 参考
- 构建系统提示词，注入世界规则 + 当前状态 + 检索片段
- 先尝试 `json_schema` 输出，失败回退 `json_object`
- 对输出做结构归一化，保证关键字段齐全：
  - `narration`
  - `dialogue`
  - `state_changes`
  - `next_options`
  - `consistency_notes`
  - `rag_sources`
- 对 `state_changes` 做一致性后验校验，不合法时追加修正说明

环境变量：
- `DEEP_SEEK_API_KEY`

### 2.3 自动化评估器

文件：`src/evaluation/auto_eval.py`

实现要点：
- `run_full_evaluation(output_path="evaluation_report.json")`
- 子评估项：
  1) `intent_recognition`
  2) `consistency_detection`
  3) `generation_latency`
  4) `branch_diversity`

具体说明：
- `_eval_intent`：读取 `intent_test.jsonl`，统计 accuracy / macro-f1 / per-class f1
- `_eval_consistency`：读取 `consistency_test.jsonl`，用一致性检查器做二分类评估
- `_eval_latency`：默认 100 轮 NLU 推理平均时延
- `_eval_diversity`：优先用故事生成器生成 10 段文本，否则使用降级文本，计算平均余弦相似度与多样性分

### 2.4 指标工具

文件：`src/evaluation/metrics.py`

实现要点：
- 封装 `classification_metrics`，统一输出：
  - `accuracy`
  - `f1_macro`
  - `per_class_f1`

### 2.5 一键评估入口

文件：`run_evaluation.py`

实现要点：
- 组装 `StateManager / LocalIntentClassifier / ConsistencyChecker / NarrativeRetriever / StoryGenerator`
- 自动处理 StoryGenerator 初始化失败（例如未配置 API Key）
- 执行 `AutoEvaluator.run_full_evaluation`
- 输出并保存 `evaluation_report.json`

---

## 3. 与 Phase2 的打通

已更新：`src/core/game_engine.py`

打通逻辑：
- 若可初始化 `NarrativeRetriever + StoryGenerator`，优先走真实生成链路
- 若生成不可用（无 key / API 异常），自动回退 Phase2 模板输出
- 保持系统可运行性与演示稳定性

---

## 4. 依赖更新

`requirements.txt` 已新增：
- `numpy`
- `scikit-learn`
- `sentence-transformers`
- `faiss-cpu`

---

## 5. 使用方法

### 5.1 安装依赖

```bash
pip install -r requirements.txt
```

### 5.2 配置 API Key（用于真实故事生成）

PowerShell：

```powershell
$env:DEEP_SEEK_API_KEY="your_key"
```

### 5.3 执行一键评估

```bash
python run_evaluation.py
```

执行后产物：
- `evaluation_report.json`

---

## 6. 已验证结果（本地执行）

已实际运行：
- `python run_evaluation.py`

结果：
- 成功输出评估报告
- 成功写入 `evaluation_report.json`

示例指标（会随模型与数据变化）：
- intent_recognition: accuracy / macro-f1
- consistency_detection: accuracy / macro-f1
- generation_latency: avg_ms
- branch_diversity: diversity_score

---

## 7. 说明与后续优化

当前实现已满足规格书 Week3 的功能要求，且具备可运行与可评估能力。

建议下一步（进入 Phase 4）：
1. 对接 `demo_controller.py` 双模式（LIVE/SCRIPTED）
2. 接入 `app.py` Gradio 页面
3. 增加导出 trace 与调试视图
4. 对故事输出 schema 做更严格字段约束和回退重试策略
