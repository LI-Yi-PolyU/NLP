from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class DemoController:
    """
    双模式演示系统：
    - LIVE: 真实引擎调用（展示实时性）
    - SCRIPTED: 关键步骤优先走缓存（保障稳定性）
    """

    def __init__(self, game_engine, mode: str = "LIVE"):
        self.engine = game_engine
        self.mode = mode.upper()
        self.cache = self._load_cache()
        self.trace_path = Path("data/benchmarks/demo_trace.jsonl")
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_cache(self) -> Dict[int, Dict]:
        fp = Path("data/benchmarks/demo_scenarios.json")
        if not fp.exists():
            return {}

        with open(fp, "r", encoding="utf-8") as f:
            scenarios = json.load(f)

        # 将演讲关键路径映射为 step->固定响应占位
        # 真正运行时，如果该步未配置固定响应，则会回落到 LIVE 调用。
        cache: Dict[int, Dict] = {}
        for scenario in scenarios:
            for idx, step in enumerate(scenario.get("steps", [])):
                cache.setdefault(
                    idx,
                    {
                        "narration": f"[SCRIPTED] 你选择了：{step.get('input', '行动')}。剧情稳定推进中。",
                        "dialogue": None,
                        "state_changes": [],
                        "next_options": [
                            {
                                "id": "A",
                                "text": "继续按演示路径前进",
                                "intent_hint": step.get("expected_intent", "ASK_INFO"),
                                "consequence_preview": "确保演示稳定",
                            }
                        ],
                        "consistency_notes": ["演示模式：使用预置响应确保关键路径稳定。"],
                        "rag_sources": [],
                    },
                )
        return cache

    def _in_critical_path(self, current_step: int) -> bool:
        return current_step in self.cache

    def _get_cached_response(self, current_step: int) -> Dict:
        return self.cache.get(current_step, self._get_fallback_response(current_step))

    @staticmethod
    def _get_fallback_response(current_step: int) -> Dict:
        return {
            "narration": f"[FALLBACK] 第 {current_step} 步使用兜底响应，系统仍可继续演示。",
            "dialogue": None,
            "state_changes": [],
            "next_options": [
                {
                    "id": "A",
                    "text": "继续",
                    "intent_hint": "ASK_INFO",
                    "consequence_preview": "低风险",
                }
            ],
            "consistency_notes": ["兜底响应触发"],
            "rag_sources": [],
        }

    def _log_interaction(self, current_step: int, user_input: str, result: Dict) -> None:
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "step": current_step,
            "mode": self.mode,
            "input": user_input,
            "result_hash": hashlib.md5(json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
            "result": result,
        }
        with open(self.trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def process_turn(self, user_input: str, current_step: int) -> Dict:
        if self.mode == "SCRIPTED" and self._in_critical_path(current_step):
            result = self._get_cached_response(current_step)
            self._log_interaction(current_step, user_input, result)
            return result

        try:
            result = self.engine.process_turn(user_input)
            self._log_interaction(current_step, user_input, result)
            return result
        except Exception:
            if self.mode == "SCRIPTED":
                result = self._get_fallback_response(current_step)
                self._log_interaction(current_step, user_input, result)
                return result
            raise

    def get_debug_view(self) -> Dict:
        return {
            "mode": self.mode,
            "current_intent": self.engine.last_intent,
            "fact_db_snapshot": self.engine.state.get_current_state(),
            "consistency_check_result": self.engine.last_consistency_result,
            "rag_retrieved_items": self.engine.last_retrieved_scenarios,
            "game_over": getattr(self.engine, "game_over", False),
            "turn_count": getattr(self.engine, "turn_count", 0),
            "ending_type": (getattr(self.engine, "ending_payload", {}) or {}).get("ending_type"),
            "trace_file": str(self.trace_path),
        }

    def export_trace(self, output_path: str = "data/benchmarks/exported_trace.json") -> str:
        lines: List[Dict] = []
        if self.trace_path.exists():
            with open(self.trace_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(json.loads(line))

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(lines, f, ensure_ascii=False, indent=2)
        return str(out)
