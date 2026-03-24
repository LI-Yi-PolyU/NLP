from __future__ import annotations

import json

import yaml

from src.core.game_engine import GameEngine
from src.core.consistency_checker import ConsistencyChecker
from src.core.state_manager import StateManager
from src.evaluation.auto_eval import AutoEvaluator
from src.generation.retriever import NarrativeRetriever
from src.generation.story_gen import StoryGenerator
from src.nlu.local_bert import LocalIntentClassifier


def main() -> None:
    with open("config/model_config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    engine = GameEngine()
    state = engine.state
    nlu = engine.local_nlu
    checker = engine.checker
    retriever = engine.retriever or NarrativeRetriever()

    story_generator = engine.story_generator
    if story_generator is None:
        try:
            story_generator = StoryGenerator(cfg, retriever, state, checker)
        except Exception as exc:
            print(f"[WARN] StoryGenerator 未启用，将跳过真实生成多样性评估: {exc}")

    evaluator = AutoEvaluator(
        nlu,
        checker,
        state,
        story_generator=story_generator,
        game_engine=engine,
    )
    report = evaluator.run_full_evaluation("evaluation_report.json")

    print("评估完成，结果已写入 evaluation_report.json")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
