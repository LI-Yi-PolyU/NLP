# StoryWeaver Phase 1 完成说明与使用指南

## 1. 结论

Phase 1 已完成（对应规格书中的 Step 1.1, Step 1.2, Step 1.3）。

已完成的核心目标：
- 建立配置模板与项目基础目录
- 实现一键数据流水线（意图数据、一致性基准、RAG 语料、演示路径）
- 提供数据格式校验工具
- 实际生成并验证了基准数据

说明：规格书目录里写 intent_train 为 500 条，但函数签名要求是 n_train=400, n_test=100，当前实现严格按函数签名执行（总计 500 条样本）。

---

## 2. Phase 1 做了什么

### 2.1 配置与模板

已创建并可直接使用：
- config/world_setting.yaml
  - 定义世界观、地点、角色、物品、硬约束规则
- config/model_config.yaml
  - 已配置 DeepSeek API 地址与模型
  - local 段已切换为中文模型配置（bert-base-chinese / 中文 NLI / 中文 embedding）
- config/prompts/intent_classification.txt
- config/prompts/story_generation.json
- config/prompts/consistency_rules.yaml

### 2.2 数据流水线

文件：run_data_pipeline.py

已实现函数：
- generate_intent_dataset(n_train=400, n_test=100, output_dir="data/benchmarks")
  - 从世界配置读取实体
  - 模板生成多意图样本
  - 注入 10% UNKNOWN 噪声样本
  - 生成 intent_train.jsonl 与 intent_test.jsonl

- generate_consistency_benchmark(n_pairs=200, output_path="data/benchmarks/consistency_test.jsonl")
  - 基于硬规则自动生成一致/冲突样本
  - 50% CONSISTENT + 50% CONFLICT

- build_rag_corpus(output_dir="data/raw_corpus")
  - 优先调用 API 生成高质量叙事片段
  - 若 API 不稳定，自动模板补齐到 300 条
  - 生成字段包含：id, setting, location, characters, plot_summary, text_segment, source

- 内置生成演示路径：demo_scenarios.json（3 条）

### 2.3 数据校验器

文件：src/data_validator.py

已实现函数：
- validate_intent_data(file_path: str) -> bool

校验内容包括：
- JSONL 可解析
- 必填字段存在
- intent 标签合法
- entities 为列表
- 实体 span 与文本切片一致

---

## 3. 当前产物清单

- data/benchmarks/intent_train.jsonl
- data/benchmarks/intent_test.jsonl
- data/benchmarks/consistency_test.jsonl
- data/benchmarks/demo_scenarios.json
- data/raw_corpus/synthetic_scenarios.jsonl

---

## 4. 当前数据规模与状态

已验证规模：
- intent_train.jsonl: 400
- intent_test.jsonl: 100
- consistency_test.jsonl: 200
- synthetic_scenarios.jsonl: 300

已验证质量：
- validate_intent_data(intent_train.jsonl) = True
- validate_intent_data(intent_test.jsonl) = True

RAG 语料已支持 API 产出，source 字段可看到 api/template 来源。

---

## 5. 应该怎么使用

### 5.1 环境准备

1) 安装依赖
- pip install -r requirements.txt

2) 配置 API 环境变量（仅环境变量读取）
- Windows PowerShell 临时会话：
  $env:DEEP_SEEK_API_KEY="你的密钥"

- Windows 系统永久变量（建议）：
  在系统环境变量中新增 DEEP_SEEK_API_KEY

### 5.2 一键生成全部 Phase 1 数据

- python run_data_pipeline.py

执行后将自动生成：
- 意图训练/测试数据
- 一致性基准数据
- RAG 语料
- 演示路径数据

### 5.3 校验数据是否可用

- python -c "from src.data_validator import validate_intent_data; print(validate_intent_data('data/benchmarks/intent_train.jsonl'))"
- python -c "from src.data_validator import validate_intent_data; print(validate_intent_data('data/benchmarks/intent_test.jsonl'))"

### 5.4 重新生成不同规模（可选）

在 Python 中手动调用：
- from run_data_pipeline import generate_intent_dataset
- generate_intent_dataset(n_train=450, n_test=100)

---

## 6. Phase 1 在整体项目中的作用

- 为 Phase 2 的 NLU 提供可训练、可评估的标准数据
- 为一致性检查器提供可回归测试样本
- 为后续 RAG 检索与故事生成提供基础语料库
- 为演示提供固定路径，提升答辩稳定性

换句话说，Phase 1 是整个项目的“数据地基”，后续所有模块都依赖它。

---

## 7. 推荐下一步

- 进入 Phase 2：先实现 src/nlu/local_bert.py 与 src/core/state_manager.py
- 然后打通最小闭环：意图识别 -> 状态更新 -> 一致性检查 -> 返回结构化结果
- 最后再接入 RAG 检索与完整生成链路
