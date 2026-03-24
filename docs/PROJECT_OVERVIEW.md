# StoryWeaver 项目说明

## 1. 项目做了什么
StoryWeaver 是一个面向多轮交互的 AI 文本冒险系统。项目核心目标是把自然语言理解、状态管理、一致性约束和剧情生成连接成一个可运行、可评测、可演示的完整流程。

系统支持两种交互方式：
- 自由文本输入，例如“与长者交谈”“前往洞穴”
- 选项驱动输入，基于上一轮给出的下一步行动

系统输出为结构化结果，包含：
- 叙事文本
- 可选对话
- 状态变化提议
- 下一步选项
- 一致性备注与来源信息

项目同时覆盖了课程要求的三类能力：
- NLU：意图识别与实体抽取
- NLG：上下文感知剧情生成
- Consistency：状态一致性检查与修复

## 2. 项目整体流程
项目分为离线流程与在线流程两部分。

### 2.1 离线流程（数据与评测准备）
1. 读取世界观与模型配置
2. 生成意图识别数据集（训练/测试）
3. 生成一致性对抗测试集
4. 构建叙事语料（用于检索与示例）
5. 生成演示路径样例

入口脚本：
- [run_data_pipeline.py](run_data_pipeline.py)

### 2.2 在线流程（每轮交互）
1. 接收玩家输入
2. NLU 识别意图与实体
3. 将意图映射为结构化事实变更
4. 执行一致性校验（硬规则、数据库冲突、语义冲突）
5. 调用生成模块输出剧情与选项
6. 回写状态并记录轨迹
7. 前端流式展示结果

核心调用链：
- [app.py](app.py)
- [src/demo/demo_controller.py](src/demo/demo_controller.py)
- [src/core/game_engine.py](src/core/game_engine.py)
- [src/core/consistency_checker.py](src/core/consistency_checker.py)
- [src/generation/story_gen.py](src/generation/story_gen.py)

## 3. 关键模块与职责
### 3.1 配置与提示词
- [config/world_setting.yaml](config/world_setting.yaml)：世界观、地点、角色、物品、硬规则
- [config/model_config.yaml](config/model_config.yaml)：模型与推理配置
- [config/prompts](config/prompts)：提示词与输出结构约束

### 3.2 NLU
- [src/nlu/local_bert.py](src/nlu/local_bert.py)：本地意图识别主流程（含可训练轻量分类分支与回退策略）
- [src/nlu/api_fallback.py](src/nlu/api_fallback.py)：低置信输入的 API 回退识别
- [src/nlu/entity_extractor.py](src/nlu/entity_extractor.py)：实体抽取

### 3.3 状态与一致性
- [src/core/state_manager.py](src/core/state_manager.py)：事实库存储、状态快照与状态更新
- [src/core/consistency_checker.py](src/core/consistency_checker.py)：三层一致性检查与自动修复策略
- [src/core/game_engine.py](src/core/game_engine.py)：单轮主协调器（NLU -> 状态 -> 生成 -> 回写）

### 3.4 生成与检索
- [src/generation/retriever.py](src/generation/retriever.py)：叙事检索（向量索引）
- [src/generation/story_gen.py](src/generation/story_gen.py)：结构化剧情生成与后处理

### 3.5 评测与演示
- [src/evaluation/auto_eval.py](src/evaluation/auto_eval.py)：自动评测
- [run_evaluation.py](run_evaluation.py)：评测入口
- [src/demo/demo_controller.py](src/demo/demo_controller.py)：LIVE/SCRIPTED 双模式演示控制
- [app.py](app.py)：Gradio 前端与流式交互

## 4. 评测数据放在哪里
### 4.1 基准与测试数据
目录：
- [data/benchmarks](data/benchmarks)

主要文件：
- [data/benchmarks/intent_train.jsonl](data/benchmarks/intent_train.jsonl)：意图训练集
- [data/benchmarks/intent_test.jsonl](data/benchmarks/intent_test.jsonl)：意图测试集
- [data/benchmarks/consistency_test.jsonl](data/benchmarks/consistency_test.jsonl)：一致性对抗测试集
- [data/benchmarks/demo_scenarios.json](data/benchmarks/demo_scenarios.json)：演示缓存路径
- [data/benchmarks/demo_trace.jsonl](data/benchmarks/demo_trace.jsonl)：交互轨迹日志
- [data/benchmarks/exported_trace.json](data/benchmarks/exported_trace.json)：导出的演示轨迹
- [data/benchmarks/day3_evidence.json](data/benchmarks/day3_evidence.json)：Day3 证据聚合结果

### 4.2 评测报告
- [evaluation_report.json](evaluation_report.json)：最新自动评测报告

## 5. 目前可直接复用的交付物
### 5.1 Day1/Day2/Day3 分包目录
- [day1](day1)：Day1 代码与文档
- [day2](day2)：Day2 代码与文档
- [day3](day3)：Day3 代码、文档与证据产物

### 5.2 答辩文档
- [DAY3_答辩证据包.md](DAY3_答辩证据包.md)
- [DAY3_评分对齐说明.md](DAY3_评分对齐说明.md)
- [小组项目简报.md](小组项目简报.md)

## 6. 如何运行
### 6.1 数据流水线
python run_data_pipeline.py

### 6.2 自动评测
python run_evaluation.py

### 6.3 证据导出
python run_day3_evidence.py

### 6.4 启动界面
python app.py

说明：
- 若要启用在线 API 生成，请先配置 DEEP_SEEK_API_KEY 环境变量。
- 不配置 API Key 时，系统仍可运行本地流程并输出可复现实验结果。

## 7. 项目当前状态（整理版）
已完成：
- 端到端交互链路（含流式展示）
- 意图识别与回退机制
- 状态持久化与一致性检查
- 结构化剧情生成
- 自动评测与报告输出
- 演示证据导出

仍建议继续优化：
- 增强外推测试，降低同分布评测偏高风险
- 增加人工评测协议（可读性、可玩性、分支差异）
- 优化长程剧情下的状态压缩与检索效率
