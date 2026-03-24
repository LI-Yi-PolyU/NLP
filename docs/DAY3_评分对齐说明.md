# StoryWeaver Day3 评分对齐说明

## 目标
本文件用于将项目产物与评分标准逐项对齐，支持答辩讲解与证据引用。

## 一、Appropriateness（适当性）
- 任务设定与实现链路匹配：NLU -> State -> Consistency -> Generation -> Demo。
- 证据：
  - 评估报告: evaluation_report.json
  - 演示轨迹: data/benchmarks/exported_trace.json
  - 证据包: DAY3_答辩证据包.md

## 二、Soundness（严谨性）
- 已具备自动评估流水线，覆盖 intent、consistency、latency、diversity。
- 一致性检查提供硬规则 + DB核对 + 语义层。
- 证据：
  - 评估入口: run_evaluation.py
  - 一致性模块: src/core/consistency_checker.py
  - 指标报告: evaluation_report.json

## 三、Excitement（吸引力）
- 剧情分支与演示轨迹可展示多种路径。
- LIVE/SCRIPTED 双模式可兼顾实时性和稳定性。
- 证据：
  - demo_scenarios: data/benchmarks/demo_scenarios.json
  - 交互trace: data/benchmarks/demo_trace.jsonl

## 四、Presentation（演讲表现）
- 提供可导出的证据包（Markdown + JSON）用于现场展示。
- 提供调试面板与状态快照，支持“可解释演示”。
- 证据：
  - 证据脚本: run_day3_evidence.py
  - 导出结果: DAY3_答辩证据包.md, data/benchmarks/day3_evidence.json

## 五、Writing（写作）
- 技术说明按 Phase 拆分，且新增 Day3 对齐说明与证据包文档。
- 建议答辩材料引用顺序：
  1. DAY3_答辩证据包.md
  2. evaluation_report.json
  3. PHASE4_完成说明与使用指南.md

## 建议口径
- 若 API 未开启，明确声明多样性指标使用本地回退样本，仅作流程验证。
- 对高分结果说明“同分布评估条件”，并补充外推测试作为风险控制。
