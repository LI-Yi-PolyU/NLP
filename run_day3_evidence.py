from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


TRACE_JSON = Path("data/benchmarks/exported_trace.json")
TRACE_JSONL = Path("data/benchmarks/demo_trace.jsonl")
EVAL_REPORT = Path("evaluation_report.json")
OUT_JSON = Path("data/benchmarks/day3_evidence.json")
OUT_MD = Path("DAY3_答辩证据包.md")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _has_cjk(text: str) -> bool:
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False


def _to_trace_rows() -> List[Dict[str, Any]]:
    exported = _load_json(TRACE_JSON, default=[])
    rows: List[Dict[str, Any]] = []
    if isinstance(exported, list):
        rows.extend([x for x in exported if isinstance(x, dict)])

    if not rows:
        rows = _load_jsonl(TRACE_JSONL)

    return rows


def _normalize_notes(raw_notes: Any) -> List[str]:
    if isinstance(raw_notes, list):
        return [str(x) for x in raw_notes]
    if isinstance(raw_notes, str):
        return [raw_notes]
    return []


def _collect_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    mode_counter: Counter[str] = Counter()
    ending_counter: Counter[str] = Counter()
    scripted_fallback = 0
    non_cjk_narration = 0
    consistency_blocked = 0

    for row in rows:
        mode = str(row.get("mode", "UNKNOWN")).upper()
        mode_counter[mode] += 1

        result = row.get("result", {}) if isinstance(row.get("result"), dict) else {}
        narration = str(result.get("narration", ""))
        notes = _normalize_notes(result.get("consistency_notes"))

        if "[FALLBACK]" in narration:
            scripted_fallback += 1

        if narration and not _has_cjk(narration):
            non_cjk_narration += 1

        if any("未通过一致性检查" in n for n in notes):
            consistency_blocked += 1

        ending_type = str(result.get("ending_type", "")).strip()
        if ending_type:
            ending_counter[ending_type] += 1

    return {
        "trace_total": len(rows),
        "mode_distribution": dict(mode_counter),
        "ending_distribution": dict(ending_counter),
        "scripted_fallback_count": scripted_fallback,
        "non_cjk_narration_count": non_cjk_narration,
        "consistency_blocked_count": consistency_blocked,
    }


def _find_evidence_cases(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []

    for row in rows:
        result = row.get("result", {}) if isinstance(row.get("result"), dict) else {}
        narration = str(result.get("narration", ""))
        if row.get("mode") == "SCRIPTED" and "[SCRIPTED]" in narration:
            cases.append(
                {
                    "type": "SCRIPTED_STABILITY",
                    "timestamp": row.get("timestamp"),
                    "input": row.get("input"),
                    "narration": narration[:180],
                }
            )
            break

    for row in rows:
        result = row.get("result", {}) if isinstance(row.get("result"), dict) else {}
        notes = _normalize_notes(result.get("consistency_notes"))
        hit = next((n for n in notes if "自动修正" in n), "")
        if hit:
            cases.append(
                {
                    "type": "CONSISTENCY_AUTO_FIX",
                    "timestamp": row.get("timestamp"),
                    "input": row.get("input"),
                    "note": hit,
                }
            )
            break

    for row in rows:
        result = row.get("result", {}) if isinstance(row.get("result"), dict) else {}
        ending = str(result.get("ending_type", "")).strip()
        if ending:
            cases.append(
                {
                    "type": "ENDING_TRIGGER",
                    "timestamp": row.get("timestamp"),
                    "input": row.get("input"),
                    "ending_type": ending,
                    "narration": str(result.get("narration", ""))[:180],
                }
            )
            break

    return cases


def _build_score_mapping(eval_report: Dict[str, Any], stats: Dict[str, Any]) -> Dict[str, Any]:
    intent_acc = float(eval_report.get("intent_recognition", {}).get("accuracy", 0.0) or 0.0)
    consistency_acc = float(eval_report.get("consistency_detection", {}).get("accuracy", 0.0) or 0.0)
    latency_ms = float(eval_report.get("generation_latency", {}).get("avg_ms", 0.0) or 0.0)

    # Day3 口径：按展示可解释性 + 指标完整性给出保守估算。
    appropriateness = 2.8 if intent_acc >= 0.8 else 2.5
    soundness = 2.8 if consistency_acc >= 0.8 else 2.4
    excitement = 2.7 if stats.get("trace_total", 0) >= 20 else 2.4
    presentation = 2.8 if latency_ms <= 80 and stats.get("mode_distribution", {}).get("SCRIPTED", 0) > 0 else 2.5
    writing = 2.7

    total = round(appropriateness + soundness + excitement + presentation + writing, 2)

    return {
        "appropriateness": appropriateness,
        "soundness": soundness,
        "excitement": excitement,
        "presentation": presentation,
        "writing": writing,
        "total": total,
        "note": "该分数为答辩彩排估分，非最终评分。",
    }


def _write_markdown(payload: Dict[str, Any]) -> None:
    eval_report = payload.get("evaluation", {})
    stats = payload.get("trace_stats", {})
    score = payload.get("score_estimate", {})
    cases = payload.get("evidence_cases", [])

    lines: List[str] = []
    lines.append("# StoryWeaver Day3 答辩证据包")
    lines.append("")
    lines.append("## 1. 评估快照")
    lines.append("")
    lines.append(f"- 意图识别准确率: {eval_report.get('intent_recognition', {}).get('accuracy', 0)}")
    lines.append(f"- 一致性检测准确率: {eval_report.get('consistency_detection', {}).get('accuracy', 0)}")
    lines.append(f"- 端到端平均延迟(ms): {eval_report.get('generation_latency', {}).get('avg_ms', 0)}")
    lines.append(f"- 延迟模式: {eval_report.get('generation_latency', {}).get('mode', 'unknown')}")
    lines.append("")
    lines.append("## 2. 演示轨迹统计")
    lines.append("")
    lines.append(f"- Trace 总条数: {stats.get('trace_total', 0)}")
    lines.append(f"- 模式分布: {json.dumps(stats.get('mode_distribution', {}), ensure_ascii=False)}")
    lines.append(f"- 结局分布: {json.dumps(stats.get('ending_distribution', {}), ensure_ascii=False)}")
    lines.append(f"- SCRIPTED 兜底触发数: {stats.get('scripted_fallback_count', 0)}")
    lines.append(f"- 非中文叙事条数: {stats.get('non_cjk_narration_count', 0)}")
    lines.append(f"- 一致性拦截条数: {stats.get('consistency_blocked_count', 0)}")
    lines.append("")
    lines.append("## 3. 关键证据样例")
    lines.append("")
    if not cases:
        lines.append("- 暂无可用样例")
    else:
        for idx, case in enumerate(cases, start=1):
            lines.append(f"### 样例 {idx}: {case.get('type', 'UNKNOWN')}")
            lines.append(f"- 时间: {case.get('timestamp', '')}")
            lines.append(f"- 输入: {case.get('input', '')}")
            if case.get("narration"):
                lines.append(f"- 叙事摘要: {case.get('narration')}")
            if case.get("note"):
                lines.append(f"- 备注: {case.get('note')}")
            if case.get("ending_type"):
                lines.append(f"- 结局类型: {case.get('ending_type')}")
            lines.append("")

    lines.append("## 4. 评分维度映射（彩排估分）")
    lines.append("")
    lines.append(f"- Appropriateness: {score.get('appropriateness', 0)} / 3")
    lines.append(f"- Soundness: {score.get('soundness', 0)} / 3")
    lines.append(f"- Excitement: {score.get('excitement', 0)} / 3")
    lines.append(f"- Presentation: {score.get('presentation', 0)} / 3")
    lines.append(f"- Writing: {score.get('writing', 0)} / 3")
    lines.append(f"- 总分: {score.get('total', 0)} / 15")
    lines.append(f"- 说明: {score.get('note', '')}")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")


def main() -> None:
    eval_report = _load_json(EVAL_REPORT, default={})
    rows = _to_trace_rows()
    stats = _collect_stats(rows)
    cases = _find_evidence_cases(rows)
    score = _build_score_mapping(eval_report, stats)

    payload = {
        "evaluation": eval_report,
        "trace_stats": stats,
        "evidence_cases": cases,
        "score_estimate": score,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    _write_markdown(payload)

    print(f"[Day3] 证据JSON已生成: {OUT_JSON}")
    print(f"[Day3] 证据Markdown已生成: {OUT_MD}")


if __name__ == "__main__":
    main()
