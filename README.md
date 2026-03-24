# StoryWeaver

StoryWeaver 是一个面向课程项目的 AI 文本冒险系统，核心目标是把“意图理解 -> 世界状态更新 -> 一致性校验 -> 叙事生成 -> 评测导出”串成可演示、可复现实验链路。

系统支持两种体验模式：

- LIVE：走真实链路（本地 NLU + 规则 + 生成器）
- SCRIPTED：走预置脚本，保证演示稳定和低延迟

## 主要能力

- 本地 NLU：意图识别（含线性分类/规则回退）+ 实体抽取
- 一致性校验：硬规则 + 状态冲突检测 + 可修复策略
- 状态管理：基于事实库（Fact）维护玩家位置、物品、角色状态
- 剧情生成：结合检索与生成（可接 DeepSeek API）
- 可视化演示：Gradio 交互界面、回合/主线阶段/调试信息展示
- 自动评测：意图准确率、一致性准确率、端到端延迟、多样性
- 证据导出：答辩证据 JSON + Markdown 报告

## 技术栈

- Python 3.10+
- Gradio
- transformers / torch
- scikit-learn
- sentence-transformers + faiss-cpu
- PyYAML
- OpenAI Python SDK（以 OpenAI 兼容方式调用 DeepSeek）

## 快速开始

### 1. 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 配置可选 API Key（用于生成与回退）

如果你希望启用 DeepSeek 生成链路，请设置环境变量：

```powershell
$env:DEEP_SEEK_API_KEY = "你的_key"
```

如果不设置，系统会自动退回本地/模板路径，仍可运行演示与评测。

### 3. 启动应用

```powershell
python app.py
```

或使用项目自带重启脚本（会先清理 7860-7869 端口占用再启动）：

```powershell
powershell -ExecutionPolicy Bypass -File .\restart_app.ps1
```

启动后访问终端输出的本地地址（默认从 7860 起自动选可用端口）。

## 评测与数据流程

### 1. 生成/刷新评测数据

```powershell
python run_data_pipeline.py
```

默认会在 data/benchmarks 下生成：

- intent_train.jsonl
- intent_test.jsonl
- consistency_test.jsonl

并在 data/raw_corpus 下生成语料文件。

### 2. 执行自动评测

```powershell
python run_evaluation.py
```

输出文件：

- evaluation_report.json

评测项包括：

- intent_recognition
- consistency_detection
- generation_latency（端到端 GameEngine 口径）
- branch_diversity

### 3. 导出答辩证据包

```powershell
python run_day3_evidence.py
```

输出文件：

- data/benchmarks/day3_evidence.json
- DAY3_答辩证据包.md

## 项目结构（核心）

```text
.
├─ app.py                         # Gradio 入口
├─ run_data_pipeline.py           # 数据集与语料构建
├─ run_evaluation.py              # 自动评测入口
├─ run_day3_evidence.py           # Day3 证据导出
├─ restart_app.ps1                # 清端口并重启应用
├─ config/                        # 模型、世界观、提示词配置
├─ data/
│  ├─ benchmarks/                 # 评测集与评测产物
│  ├─ raw_corpus/                 # 合成语料
│  └─ vector_index/               # 向量索引产物
├─ src/
│  ├─ core/                       # game_engine / state_manager / consistency_checker
│  ├─ nlu/                        # 本地识别与 API fallback
│  ├─ generation/                 # 检索与故事生成
│  ├─ evaluation/                 # 自动评测逻辑
│  └─ demo/                       # 演示控制与可视化
├─ docs/                          # 所有项目文档（已集中归档）
├─ day1/ day2/ day3/              # 阶段性交付归档
└─ readme.md                      # 当前项目总说明（本文件）
```

## 文档索引

项目说明与阶段文档已统一放在 docs 目录，建议优先阅读：

- docs/PROJECT_OVERVIEW.md
- docs/StoryWeaver_技术规格书_现状对齐.md
- docs/PHASE1_完成说明与使用指南.md
- docs/PHASE2_完成说明与实现细节.md
- docs/PHASE3_完成说明与使用指南.md
- docs/PHASE4_完成说明与使用指南.md
- docs/DAY3_评分对齐说明.md

## 常见问题

### 1) 启动失败或端口被占用

- 先执行 restart_app.ps1 清理 7860-7869 端口
- 或手动结束占用进程后再运行 python app.py

### 2) 没有配置 API Key

- 可正常运行，但会更多走本地/模板策略
- 若要完整体验生成链路，请设置 DEEP_SEEK_API_KEY

### 3) 首次运行模型下载慢

- transformers 相关模型首次加载会较慢，属于正常现象
- 建议保持网络稳定并预留缓存目录空间

## 许可与用途

本项目用于课程实验与演示，非生产级系统。若用于扩展开发，建议补充：

- 更完善的单元测试与回归测试
- 可观测性（结构化日志、指标监控）
- 配置管理与部署脚本规范化
