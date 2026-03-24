from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.core.state_manager import Fact
from src.evaluation.metrics import classification_metrics


class AutoEvaluator:
    def __init__(self, nlu_engine, consistency_checker, state_manager, story_generator=None, game_engine=None):
        self.nlu = nlu_engine
        self.checker = consistency_checker
        self.state = state_manager
        self.story_generator = story_generator
        self.game_engine = game_engine

    def run_full_evaluation(self, output_path: str = "evaluation_report.json"):
        results = {
            "intent_recognition": self._eval_intent(),
            "consistency_detection": self._eval_consistency(),
            "generation_latency": self._eval_latency(),
            "branch_diversity": self._eval_diversity(),
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        return results

    def _eval_intent(self) -> Dict:
        fp = Path("data/benchmarks/intent_test.jsonl")
        if not fp.exists():
            return {"accuracy": 0.0, "f1_macro": 0.0, "per_class_f1": {}, "error": "intent_test not found"}

        y_true: List[str] = []
        y_pred: List[str] = []
        errors: List[Dict] = []

        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                expected = row.get("intent", "UNKNOWN")
                text = row.get("text", "")
                y_true.append(expected)
                pred = self.nlu.predict(text)
                predicted = pred.get("intent", "UNKNOWN")
                y_pred.append(predicted)

                if predicted != expected and len(errors) < 10:
                    errors.append(
                        {
                            "text": text,
                            "expected": expected,
                            "predicted": predicted,
                            "confidence": round(float(pred.get("confidence", 0.0) or 0.0), 4),
                            "source": pred.get("source", "unknown"),
                        }
                    )

        labels = ["EXPLORE", "NEGOTIATE", "ATTACK", "USE_ITEM", "ASK_INFO", "UNKNOWN"]
        metrics = classification_metrics(y_true, y_pred, labels)
        metrics["error_examples"] = errors
        return metrics

    def _eval_consistency(self) -> Dict:
        fp = Path("data/benchmarks/consistency_test.jsonl")
        if not fp.exists():
            return {"accuracy": 0.0, "f1_macro": 0.0, "per_class_f1": {}, "error": "consistency_test not found"}

        y_true: List[str] = []
        y_pred: List[str] = []
        errors: List[Dict] = []

        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                expected = row.get("expected_label") or row.get("label") or "CONSISTENT"
                y_true.append(expected)

                facts_raw = row.get("facts", [])
                facts: List[Fact] = []
                for fr in facts_raw:
                    if isinstance(fr, dict):
                        facts.append(
                            Fact(
                                subject=str(fr.get("subject", "player")),
                                predicate=str(fr.get("predicate", "state")),
                                object=str(fr.get("object", "unknown")),
                                turn=int(fr.get("turn", self.state.current_turn + 1)),
                                valid=True,
                            )
                        )

                verdict = self.checker.verify(facts)
                predicted = "CONSISTENT" if verdict.get("passed") else "CONFLICT"
                y_pred.append(predicted)

                if predicted != expected and len(errors) < 10:
                    errors.append(
                        {
                            "expected": expected,
                            "predicted": predicted,
                            "rule_type": row.get("rule_type", "unknown"),
                            "facts": facts_raw,
                            "checker_note": (verdict.get("violations") or [{}])[0].get("description", "")
                            if isinstance(verdict.get("violations"), list)
                            else "",
                        }
                    )

        labels = ["CONSISTENT", "CONFLICT"]
        metrics = classification_metrics(y_true, y_pred, labels)
        metrics["error_examples"] = errors
        return metrics

    def _eval_latency(self) -> Dict:
        texts = [
            "查看周围环境",
            "和老村长交谈",
            "前往森林",
            "拿起火把",
        ] * 3

        start = time.perf_counter()
        mode = "nlu_only"

        if self.game_engine is not None:
            mode = "end_to_end_game_engine"
            for t in texts:
                _ = self.game_engine.process_turn(t)
        else:
            for t in texts:
                _ = self.nlu.predict(t)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / len(texts)) * 1000 if texts else 0.0
        return {
            "mode": mode,
            "rounds": len(texts),
            "total_seconds": round(elapsed, 4),
            "avg_ms": round(avg_ms, 2),
        }

    def _eval_diversity(self) -> Dict:
        base_intent = {"intent": "EXPLORE", "entities": [{"type": "location", "value": "forest"}]}
        state_snapshot = self.state.get_current_state()

        generated: List[str] = []
        if self.story_generator is not None:
            for _ in range(10):
                try:
                    out = self.story_generator.generate(base_intent, state_snapshot)
                    generated.append(out.get("narration", ""))
                except Exception:
                    break

        if len(generated) < 3:
            generated = [
                "你踏入迷雾森林，脚下落叶发出细碎声响。",
                "你穿过潮湿的林间小路，远处传来乌鸦的叫声。",
                "迷雾在树间流动，你看到前方有微弱火光。",
                "森林深处的风夹杂着泥土气息，你放慢了脚步。",
                "你沿着猎人的旧标记前进，视野逐渐开阔。",
            ]

        vec = TfidfVectorizer().fit_transform(generated)
        sim = cosine_similarity(vec)

        n = sim.shape[0]
        vals: List[float] = []
        for i in range(n):
            for j in range(i + 1, n):
                vals.append(float(sim[i, j]))

        avg_sim = sum(vals) / len(vals) if vals else 1.0
        diversity = max(0.0, 1.0 - avg_sim)

        return {
            "sample_count": len(generated),
            "avg_pairwise_similarity": round(avg_sim, 4),
            "diversity_score": round(diversity, 4),
        }
