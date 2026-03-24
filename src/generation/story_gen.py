from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

import yaml
from openai import OpenAI

from src.core.consistency_checker import ConsistencyChecker
from src.core.state_manager import Fact, StateManager


class StoryGenerator:
    def __init__(
        self,
        config: Dict,
        retriever,
        state_manager: StateManager,
        consistency_checker: Optional[ConsistencyChecker] = None,
    ):
        api_cfg = config.get("api", {})
        api_key = os.getenv("DEEP_SEEK_API_KEY", "")
        if not api_key:
            raise ValueError("缺少 DEEP_SEEK_API_KEY，无法调用故事生成 API。")

        self.client = OpenAI(api_key=api_key, base_url=api_cfg.get("base_url"))
        self.model = api_cfg.get("model_generation", "deepseek-chat")
        self.retriever = retriever
        self.state = state_manager
        self.checker = consistency_checker

    def generate(self, intent_result: Dict, state_snapshot: Dict) -> Dict:
        retrieved = self.retriever.retrieve(
            f"{intent_result.get('intent', 'ASK_INFO')} at {state_snapshot.get('player', {}).get('location', 'unknown')}",
            state_snapshot.get("player", {}).get("location", "unknown"),
            k=3,
        )

        system_prompt = self._build_system_prompt(state_snapshot, retrieved)
        user_prompt = f"玩家意图：{json.dumps(intent_result, ensure_ascii=False)}\n当前状态：{json.dumps(state_snapshot, ensure_ascii=False)}"

        schema = self._get_output_schema()

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_schema", "json_schema": {"name": "story_output", "schema": schema}},
                temperature=0.7,
                max_tokens=700,
            )
        except Exception:
            # 部分兼容接口不支持 json_schema，回退 json_object
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=700,
            )

        content = response.choices[0].message.content or "{}"
        result = self._safe_load_json(content)
        result = self._normalize_output(result, retrieved)
        result = self._force_chinese_output(result, intent_result, state_snapshot)

        return self._validate_output(result, state_snapshot)

    @staticmethod
    def _safe_load_json(content: str) -> Dict:
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)

        try:
            return json.loads(content)
        except Exception:
            return {}

    @staticmethod
    def _normalize_output(result: Dict, retrieved: List[Dict]) -> Dict:
        raw_options = result.get("next_options", [])
        normalized_options: List[Dict] = []
        if isinstance(raw_options, list):
            for idx, opt in enumerate(raw_options):
                if isinstance(opt, dict):
                    normalized_options.append(
                        {
                            "id": str(opt.get("id", chr(ord("A") + idx))),
                            "text": str(opt.get("text", opt.get("option", "继续行动"))),
                            "intent_hint": str(opt.get("intent_hint", "ASK_INFO")),
                            "consequence_preview": str(
                                opt.get("consequence_preview", opt.get("consequence_hint", ""))
                            ),
                        }
                    )
                elif isinstance(opt, str):
                    normalized_options.append(
                        {
                            "id": chr(ord("A") + idx),
                            "text": opt,
                            "intent_hint": "ASK_INFO",
                            "consequence_preview": "",
                        }
                    )

        raw_notes = result.get("consistency_notes", [])
        if isinstance(raw_notes, str):
            normalized_notes = [raw_notes]
        elif isinstance(raw_notes, list):
            normalized_notes = [str(x) for x in raw_notes]
        else:
            normalized_notes = []

        output = {
            "narration": result.get("narration", "你环顾四周，空气中弥漫着未知的气息。"),
            "dialogue": result.get("dialogue"),
            "state_changes": result.get("state_changes", []),
            "next_options": normalized_options,
            "consistency_notes": normalized_notes,
            "rag_sources": result.get("rag_sources", [x.get("id") for x in retrieved if x.get("id")]),
        }

        if not output["next_options"]:
            output["next_options"] = [
                {
                    "id": "A",
                    "text": "继续探索前方",
                    "intent_hint": "EXPLORE",
                    "consequence_preview": "可能发现新线索",
                },
                {
                    "id": "B",
                    "text": "与附近角色交谈",
                    "intent_hint": "NEGOTIATE",
                    "consequence_preview": "可能获得信息",
                },
            ]
        return output

    def _validate_output(self, result: Dict, state_snapshot: Dict) -> Dict:
        state_changes = result.get("state_changes", [])
        facts: List[Fact] = []
        next_turn = self.state.current_turn + 1

        for change in state_changes:
            try:
                facts.append(
                    Fact(
                        subject=str(change["subject"]),
                        predicate=str(change["predicate"]),
                        object=str(change["object"]),
                        turn=next_turn,
                        valid=True,
                    )
                )
            except Exception:
                continue

        if self.checker is None or not facts:
            return result

        verdict = self.checker.verify(facts)
        if verdict.get("passed"):
            return result

        notes = result.get("consistency_notes", [])
        notes.append("一致性校验提醒：生成的部分状态变更存在冲突，已建议修正。")
        result["consistency_notes"] = notes

        if verdict.get("can_auto_fix") and verdict.get("fixed_facts"):
            result["state_changes"] = [
                {
                    "subject": f.subject,
                    "predicate": f.predicate,
                    "object": f.object,
                    "operation": "set",
                }
                for f in verdict["fixed_facts"]
            ]

        return result

    def _build_system_prompt(self, state: Dict, retrieved_scenarios: List[Dict]) -> str:
        with open("config/world_setting.yaml", "r", encoding="utf-8") as f:
            world = yaml.safe_load(f) or {}

        rules = world.get("rules", {}).get("hard_constraints", [])
        scene_text = "\n".join(
            [f"- [{x.get('id')}] {x.get('scenario', '')}" for x in retrieved_scenarios]
        ) or "- 无"

        return (
            "你是文本冒险游戏叙事引擎。请基于世界设定和当前状态生成下一段剧情，严格保持状态一致性。\n"
            "硬性要求：输出文本必须是简体中文，不要使用英文句子。\n"
            "叙事要求：每一轮必须提供可推进主线的具体线索，不能只做氛围描写。\n"
            "行动要求：next_options中的每个选项都应包含明确后果提示，帮助玩家判断主线推进价值。\n"
            "目标导向：优先引导玩家完成‘火把准备 -> 获取洞穴情报 -> 拿到锈剑 -> 返回村庄’。\n"
            f"硬约束规则: {rules}\n"
            f"当前世界状态: {json.dumps(state, ensure_ascii=False)}\n"
            f"可参考检索片段:\n{scene_text}\n"
            "输出必须是合法JSON，字段至少包含 narration/state_changes/next_options/consistency_notes/rag_sources。"
        )

    @staticmethod
    def _has_cjk(text: str) -> bool:
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff":
                return True
        return False

    def _force_chinese_output(self, result: Dict, intent_result: Dict, state_snapshot: Dict) -> Dict:
        intent = intent_result.get("intent", "ASK_INFO")
        location = state_snapshot.get("player", {}).get("location", "未知地点")

        narration = str(result.get("narration", "")).strip()
        if not narration or not self._has_cjk(narration):
            result["narration"] = f"你决定执行{intent}行动，当前你身处{location}，周围环境随着你的选择悄然变化。"

        opts = result.get("next_options", [])
        fixed_opts: List[Dict] = []
        for idx, opt in enumerate(opts):
            if not isinstance(opt, dict):
                continue
            text = str(opt.get("text", "")).strip()
            if not text or not self._has_cjk(text):
                text = [
                    "继续探索周边区域",
                    "向附近角色询问线索",
                    "整理装备后谨慎前进",
                    "观察环境并制定下一步计划",
                ][idx % 4]
            fixed_opts.append(
                {
                    "id": str(opt.get("id", chr(ord("A") + idx))),
                    "text": text,
                    "intent_hint": str(opt.get("intent_hint", "ASK_INFO")),
                    "consequence_preview": str(opt.get("consequence_preview", "")),
                }
            )
        if fixed_opts:
            unique_opts: List[Dict] = []
            seen_text = set()
            for opt in fixed_opts:
                t = str(opt.get("text", "")).strip()
                if not t:
                    continue
                key = " ".join(t.split())
                if key in seen_text:
                    continue
                seen_text.add(key)
                unique_opts.append(opt)

            fallback_texts = [
                "继续探索周边区域",
                "向附近角色询问线索",
                "整理装备后谨慎前进",
                "观察环境并制定下一步计划",
                "检查当前持有物与状态",
                "返回上一个安全地点",
            ]
            for text in fallback_texts:
                key = " ".join(text.split())
                if key in seen_text:
                    continue
                unique_opts.append(
                    {
                        "id": "",
                        "text": text,
                        "intent_hint": "ASK_INFO",
                        "consequence_preview": "",
                    }
                )
                seen_text.add(key)
                if len(unique_opts) >= 4:
                    break

            result["next_options"] = [
                {
                    "id": chr(ord("A") + idx),
                    "text": str(opt.get("text", "继续行动")),
                    "intent_hint": str(opt.get("intent_hint", "ASK_INFO")),
                    "consequence_preview": str(opt.get("consequence_preview", "")),
                }
                for idx, opt in enumerate(unique_opts[:4])
            ]

        notes = result.get("consistency_notes", [])
        if isinstance(notes, str):
            notes = [notes]
        zh_notes: List[str] = []
        for n in notes:
            n = str(n).strip()
            if not n:
                continue
            if self._has_cjk(n):
                zh_notes.append(n)
        if not zh_notes:
            zh_notes = ["一致性检查已完成，未发现阻断性冲突。"]
        result["consistency_notes"] = zh_notes

        return result

    @staticmethod
    def _get_output_schema() -> Dict:
        with open("config/prompts/story_generation.json", "r", encoding="utf-8") as f:
            return json.load(f)
