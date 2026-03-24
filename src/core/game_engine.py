from __future__ import annotations

import ast
from typing import Dict, List
from pathlib import Path

import yaml

from src.core.consistency_checker import ConsistencyChecker
from src.core.state_manager import Fact, StateManager
from src.generation.retriever import NarrativeRetriever
from src.generation.story_gen import StoryGenerator
from src.nlu.api_fallback import APIIntentFallback
from src.nlu.local_bert import LocalIntentClassifier


class GameEngine:
    """Phase 2 主协调器：NLU -> State -> Consistency -> (Template)Generation"""

    def __init__(self, config_path: str = "config/model_config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f) or {}

        self.entity_alias_to_id = self._load_entity_aliases("config/world_setting.yaml")
        self.item_display_name = self._load_item_display_names("config/world_setting.yaml")
        self.entity_keyword_aliases = self._load_entity_keyword_aliases("config/entity_aliases.yaml")
        self.valid_location_ids = set(self.entity_alias_to_id.get("location", {}).values())

        self.state = StateManager()
        reset_on_start = self.config.get("gameplay", {}).get("reset_state_on_start", True)
        if reset_on_start:
            self.state.reset_world_state()
        self.local_nlu = LocalIntentClassifier(config_path=config_path)
        self.checker = ConsistencyChecker(self.state, config_path=config_path)

        self.api_fallback = None
        try:
            self.api_fallback = APIIntentFallback(self.config)
        except Exception:
            self.api_fallback = None

        self.fallback_threshold = 0.7

        self.retriever = None
        self.story_generator = None
        try:
            self.retriever = NarrativeRetriever()
            self.story_generator = StoryGenerator(self.config, self.retriever, self.state, self.checker)
        except Exception:
            self.retriever = None
            self.story_generator = None

        self.last_intent = None
        self.last_consistency_result = None
        self.last_retrieved_scenarios = []
        self.turn_count = 0
        self.game_over = False
        self.ending_payload: Dict | None = None

        self.story_endings = {
            "max_turns": 20,
            "victory": {
                "required_items": ["sword"],
                "return_location": "village",
            },
            "fail": {
                "forbidden_attack_targets": ["elder"],
            },
        }

        self.story_endings.update(self.config.get("story_endings", {}))

    @staticmethod
    def _load_entity_aliases(world_config_path: str) -> Dict[str, Dict[str, str]]:
        aliases: Dict[str, Dict[str, str]] = {
            "location": {},
            "character": {},
            "item": {},
        }
        fp = Path(world_config_path)
        if not fp.exists():
            return aliases

        with open(fp, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        world = cfg.get("world", {})

        for ent_type, key in [("location", "locations"), ("character", "characters"), ("item", "items")]:
            for row in world.get(key, []):
                ent_id = str(row.get("id", "")).strip()
                ent_name = str(row.get("name", "")).strip()
                if ent_id:
                    aliases[ent_type][ent_id] = ent_id
                if ent_name and ent_id:
                    aliases[ent_type][ent_name] = ent_id
        return aliases

    def _canonicalize_entity(self, ent_type: str, value: str) -> str:
        v = (value or "").strip()
        if not v:
            return v
        exact = self.entity_alias_to_id.get(ent_type, {}).get(v)
        if exact:
            return exact

        from_keywords = self._canonical_from_keyword_aliases(ent_type, v)
        if from_keywords:
            return from_keywords

        return v

    @staticmethod
    def _load_item_display_names(world_config_path: str) -> Dict[str, str]:
        fp = Path(world_config_path)
        if not fp.exists():
            return {}
        with open(fp, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        world = cfg.get("world", {})
        out: Dict[str, str] = {}
        for row in world.get("items", []):
            item_id = str(row.get("id", "")).strip()
            item_name = str(row.get("name", "")).strip()
            if item_id:
                out[item_id] = item_name or item_id
        return out

    @staticmethod
    def _load_entity_keyword_aliases(alias_config_path: str) -> Dict[str, Dict[str, List[str]]]:
        fp = Path(alias_config_path)
        if not fp.exists():
            return {"location": {}, "item": {}, "character": {}}
        with open(fp, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        out: Dict[str, Dict[str, List[str]]] = {"location": {}, "item": {}, "character": {}}
        for ent_type in out.keys():
            section = cfg.get(ent_type, {}) or {}
            for canonical_id, aliases in section.items():
                if isinstance(aliases, list):
                    out[ent_type][str(canonical_id)] = [str(x) for x in aliases if str(x).strip()]
        return out

    def _canonical_from_keyword_aliases(self, ent_type: str, text: str) -> str:
        aliases = self.entity_keyword_aliases.get(ent_type, {})
        for canonical_id, keywords in aliases.items():
            if any(k and k in text for k in keywords):
                return canonical_id
        return ""

    def _display_item(self, item_id: str) -> str:
        return self.item_display_name.get(item_id, item_id)

    def _infer_item_from_text(self, text: str) -> str:
        t = (text or "").strip()
        if not t:
            return ""
        return self._canonical_from_keyword_aliases("item", t)

    def process_turn(self, user_input: str) -> Dict:
        if self.game_over and self.ending_payload is not None:
            return self.ending_payload

        self.turn_count += 1
        intent_result = self.local_nlu.predict(user_input)

        if intent_result.get("confidence", 0.0) < self.fallback_threshold and self.api_fallback is not None:
            try:
                intent_result = self.api_fallback.predict(user_input)
            except Exception:
                pass

        intent_result.setdefault("raw_text", user_input)
        intent_result = self._apply_intent_guardrails(user_input, intent_result)

        self.last_intent = intent_result
        pre_state = self.state.get_current_state()

        next_turn = self.state.current_turn + 1
        proposed_facts = self._intent_to_facts(intent_result, next_turn)

        fail_target = self._forbidden_attack_target(proposed_facts)
        if fail_target:
            state_snapshot = self.state.get_current_state()
            ending = self._build_ending_response(
                "bad_forbidden_attack",
                state_snapshot,
                f"你对关键角色 {fail_target} 发起了攻击，世界秩序瞬间崩塌。",
            )
            self.game_over = True
            self.ending_payload = ending
            return ending

        consistency_result = self.checker.verify(proposed_facts)
        self.last_consistency_result = consistency_result

        applied_facts = proposed_facts
        notes: List[str] = []

        if consistency_result["passed"]:
            self.state.update_state(proposed_facts)
        elif consistency_result["can_auto_fix"] and consistency_result["fixed_facts"]:
            applied_facts = consistency_result["fixed_facts"]
            self.state.update_state(applied_facts)
            notes.append("自动修正：检测到不可执行动作，已替换为安全叙事动作")
        else:
            violations = consistency_result.get("violations", [])
            if violations:
                reason = str(violations[0].get("description", "未知冲突"))
                notes.append(f"操作未通过一致性检查，状态未更新。原因：{reason}")
            else:
                notes.append("操作未通过一致性检查，状态未更新")

        state_snapshot = self.state.get_current_state()

        victory = self._is_victory_state(state_snapshot)
        timeout = self.turn_count >= int(self.story_endings.get("max_turns", 20))
        if victory:
            ending = self._build_ending_response(
                "victory",
                state_snapshot,
                "你带着关键线索与武器返回青石村，完成了主线目标。",
            )
            self.game_over = True
            self.ending_payload = ending
            return ending
        if timeout:
            ending = self._build_ending_response(
                "timeout",
                state_snapshot,
                "夜幕降临，你尚未完成主线任务，冒险暂告一段落。",
            )
            self.game_over = True
            self.ending_payload = ending
            return ending

        if self.story_generator is not None:
            try:
                generated = self.story_generator.generate(intent_result, state_snapshot)
                self.last_retrieved_scenarios = generated.get("rag_sources", [])
                generated = self._apply_pickup_output_guardrails(
                    generated,
                    intent_result,
                    pre_state,
                    state_snapshot,
                    consistency_result,
                    applied_facts,
                )
                generated = self._postprocess_generated_output(generated, state_snapshot)
                story_facts, story_apply_notes = self._apply_generated_state_changes(generated)
                if story_facts:
                    self.state.update_state(story_facts)
                    generated["state_changes"] = [
                        {
                            "subject": f.subject,
                            "predicate": f.predicate,
                            "object": f.object,
                            "operation": "set",
                        }
                        for f in story_facts
                    ]
                if story_apply_notes:
                    generated.setdefault("consistency_notes", [])
                    generated["consistency_notes"].extend(story_apply_notes)
                if notes:
                    generated.setdefault("consistency_notes", [])
                    generated["consistency_notes"].extend(notes)
                generated = self._append_mainline_guidance(generated, self.state.get_current_state())
                return generated
            except Exception:
                pass

        narration = self._render_narration(intent_result, consistency_result, state_snapshot)
        fallback_payload = {
            "narration": narration,
            "dialogue": None,
            "state_changes": [
                {
                    "subject": f.subject,
                    "predicate": f.predicate,
                    "object": f.object,
                }
                for f in applied_facts
            ],
            "next_options": self._build_next_options(intent_result, state_snapshot),
            "consistency_notes": notes,
            "rag_sources": [],
        }
        return self._append_mainline_guidance(fallback_payload, state_snapshot)

    @staticmethod
    def _extract_item_candidates(intent_result: Dict) -> List[str]:
        entities = intent_result.get("entities", [])
        items: List[str] = []
        for e in entities:
            if isinstance(e, dict) and e.get("type") == "item":
                v = str(e.get("value", "")).strip()
                if v:
                    items.append(v)
            elif isinstance(e, str) and e.strip():
                # API fallback 在少数情况下会返回字符串实体列表，保守视作候选。
                items.append(e.strip())
        return items

    def _apply_intent_guardrails(self, user_input: str, intent_result: Dict) -> Dict:
        text = (user_input or "").strip()
        if not text:
            return intent_result

        pickup_keywords = ["拿起", "捡起", "拾起", "取走", "带上", "拿上", "拿"]
        item_candidates = self._extract_item_candidates(intent_result)
        inferred_item = self._infer_item_from_text(text)
        if inferred_item and inferred_item not in item_candidates:
            item_candidates.append(inferred_item)
        if item_candidates and any(k in text for k in pickup_keywords):
            intent_result["intent"] = "USE_ITEM"
            intent_result["pickup_item_hint"] = item_candidates[0]
            intent_result["confidence"] = max(float(intent_result.get("confidence", 0.0) or 0.0), 0.86)
            intent_result["source"] = f"{intent_result.get('source', 'unknown')}+guardrail_pickup"

        inspect_keywords = ["检查", "查看", "翻", "看看"]
        inventory_targets = ["口袋", "背包", "行囊"]
        if any(k in text for k in inspect_keywords) and any(t in text for t in inventory_targets):
            intent_result["intent"] = "ASK_INFO"
            intent_result["noop_state_change"] = True
            intent_result["confidence"] = max(float(intent_result.get("confidence", 0.0) or 0.0), 0.88)
            intent_result["source"] = f"{intent_result.get('source', 'unknown')}+guardrail_inventory_check"

        return intent_result

    def _intent_to_facts(self, intent_result: Dict, turn: int) -> List[Fact]:
        if intent_result.get("noop_state_change"):
            return []

        intent = intent_result.get("intent", "ASK_INFO")
        entities = intent_result.get("entities", [])
        raw_text = str(intent_result.get("raw_text", ""))

        def pick(ent_type: str, default: str) -> str:
            for e in entities:
                if isinstance(e, dict):
                    if e.get("type") == ent_type:
                        return self._canonicalize_entity(ent_type, str(e.get("value")))
                elif isinstance(e, str) and e.strip():
                    return self._canonicalize_entity(ent_type, e.strip())
            return default

        if intent == "EXPLORE":
            state_now = self.state.get_current_state("player")
            current_loc = state_now.get("player", {}).get("location", "village")
            target = pick("location", current_loc)
            target = self._normalize_location_target(target, current_loc, raw_text)
            if target == current_loc:
                return []
            return [Fact("player", "location", target, turn, True)]

        if intent == "ATTACK":
            target = pick("character", "unknown_enemy")
            return [Fact("player", "attack", target, turn, True)]

        if intent == "USE_ITEM":
            item = pick("item", "unknown_item")
            if item == "unknown_item":
                hint = str(intent_result.get("pickup_item_hint", "")).strip()
                item = hint or self._infer_item_from_text(raw_text) or "unknown_item"
            # “拿起/拾取”是获取物品，不应按“使用物品”处理。
            pickup_keywords = ["拿起", "捡起", "拾起", "取走", "带上", "拿上", "拿"]
            if item != "unknown_item" and any(k in raw_text for k in pickup_keywords):
                intent_result["pickup_item"] = item
                if self.state.check_fact_exists("player", "holds", item):
                    intent_result["pickup_status"] = "already_holding"
                    return []
                intent_result["pickup_status"] = "picked_up"
                return [
                    Fact("player", "holds", item, turn, True),
                    Fact(item, "location", "player", turn, True),
                ]
            return [Fact("player", "use_item", item, turn, True)]

        if intent == "NEGOTIATE":
            target = pick("character", "villager")
            facts = [Fact("player", "negotiate", target, turn, True)]
            friendly_fact = self._build_friendliness_delta_fact(target, 5, turn)
            if friendly_fact is not None:
                facts.append(friendly_fact)
            return facts

        target = pick("character", "elder")
        facts = [Fact("player", "ask", target, turn, True)]
        friendly_fact = self._build_friendliness_delta_fact(target, 5, turn)
        if friendly_fact is not None:
            facts.append(friendly_fact)
        return facts

    def _build_friendliness_delta_fact(self, character_id: str, delta: int, turn: int) -> Fact | None:
        cid = (character_id or "").strip()
        if not cid:
            return None

        snapshot = self.state.get_current_state(cid)
        current_raw = snapshot.get(cid, {}).get("friendly_to_player")
        try:
            current = int(str(current_raw))
        except Exception:
            return None

        next_value = max(0, min(100, current + int(delta)))
        if next_value == current:
            return None
        return Fact(cid, "friendly_to_player", str(next_value), turn, True)

    @staticmethod
    def _is_pickup_facts(facts: List[Fact]) -> bool:
        has_hold = any(f.subject == "player" and f.predicate == "holds" for f in facts)
        has_item_loc = any(f.predicate == "location" and f.object == "player" for f in facts)
        return has_hold and has_item_loc

    def _apply_pickup_output_guardrails(
        self,
        generated: Dict,
        intent_result: Dict,
        pre_state: Dict,
        post_state: Dict,
        consistency_result: Dict,
        applied_facts: List[Fact],
    ) -> Dict:
        pickup_status = intent_result.get("pickup_status")
        pickup_item = str(intent_result.get("pickup_item", ""))
        if not pickup_status or not pickup_item:
            return generated

        item_name = self._display_item(pickup_item)
        if pickup_status == "already_holding":
            generated["narration"] = (
                f"你确认{item_name}已经在手中，无需重复拿取。"
                "你快速检查了周边环境，准备继续下一步行动。"
            )
            generated["consistency_notes"] = ["动作已处理：该物品已在你的持有中，状态保持不变。"]
            return generated

        if pickup_status == "picked_up" and consistency_result.get("passed") and self._is_pickup_facts(applied_facts):
            generated["narration"] = (
                f"你走近目标位置，稳稳拿起了{item_name}。"
                "你感到探索条件更充分，周围细节也变得清晰。"
            )
            generated["consistency_notes"] = ["动作合法：你已拿起目标物品并完成状态更新。"]
            return generated

        return generated

    def _postprocess_generated_output(self, generated: Dict, state_snapshot: Dict) -> Dict:
        options = generated.get("next_options", [])
        if not isinstance(options, list):
            options = []

        texts: List[str] = []
        for opt in options:
            if isinstance(opt, dict):
                texts.append(str(opt.get("text", "")).strip())

        unique_texts = {" ".join(t.split()) for t in texts if t}
        too_repetitive = len(unique_texts) < 3
        generic_bucket = {
            "继续行动",
            "继续探索周边区域",
            "向附近角色询问线索",
            "整理装备后谨慎前进",
            "观察环境并制定下一步计划",
        }
        mostly_generic = sum(1 for t in unique_texts if t in generic_bucket) >= 2

        if too_repetitive or mostly_generic:
            generated["next_options"] = self._build_context_options(state_snapshot)
        return generated

    def _build_mainline_guidance(self, state_snapshot: Dict) -> Dict[str, List[str] | str]:
        player = state_snapshot.get("player", {}) if isinstance(state_snapshot, dict) else {}
        loc = str(player.get("location", "village"))
        holds = set(player.get("holds", []) if isinstance(player.get("holds", []), list) else [])

        elder_friendly_raw = state_snapshot.get("elder", {}).get("friendly_to_player", "50")
        hunter_friendly_raw = state_snapshot.get("hunter", {}).get("friendly_to_player", "35")
        try:
            elder_friendly = int(str(elder_friendly_raw))
        except Exception:
            elder_friendly = 50
        try:
            hunter_friendly = int(str(hunter_friendly_raw))
        except Exception:
            hunter_friendly = 35

        if "sword" in holds and loc == "village":
            return {
                "stage": "主线完成条件已满足",
                "tips": [
                    "你已携带关键武器回到村庄，可继续与老村长对话触发结局。",
                    "若想补全支线，可先与猎人和长老分别确认后续安排。",
                ],
            }

        if "torch" not in holds:
            return {
                "stage": "准备阶段：先获取基础探索能力",
                "tips": [
                    "在村庄优先拿起火把，未持有火把时进入洞穴风险很高。",
                    "与老村长交谈可获得洞穴与锈剑的背景线索。",
                    "完成火把准备后再前往森林或洞穴推进主线。",
                ],
            }

        if loc == "village":
            hunter_tip = (
                "猎人友好度偏低，建议先在森林与其交谈 1-2 次再深入洞穴。"
                if hunter_friendly < 40
                else "猎人关系可用，前往森林获取洞穴入口细节会更稳妥。"
            )
            return {
                "stage": "调查阶段：整合情报并确定进洞路线",
                "tips": [
                    "你已具备火把，可先与老村长确认锈剑相关信息。",
                    hunter_tip,
                    "若线索充分，可直接前往洞穴尝试获取锈剑。",
                ],
            }

        if loc == "forest":
            return {
                "stage": "过渡阶段：森林线索决定洞穴风险",
                "tips": [
                    "优先与猎人阿洛交谈，确认洞穴方位和潜在威胁。",
                    "若猎人友好度低于40，继续沟通可显著提高成功率。",
                    "情报充分后立即前往洞穴，避免回合浪费。",
                ],
            }

        if loc == "cave":
            sword_tip = "锈剑仍未获取，优先搜索并拿起锈剑。" if "sword" not in holds else "已拿到锈剑，下一步返回村庄触发主线收束。"
            return {
                "stage": "终盘阶段：洞穴取剑并撤离",
                "tips": [
                    "保持火把在身以确保洞穴探索稳定。",
                    sword_tip,
                    "获取关键物后尽快返回村庄，避免超回合导致超时结局。",
                ],
            }

        return {
            "stage": "探索阶段",
            "tips": [
                "优先保证火把在手，再获取洞穴锈剑。",
                "与关键NPC交谈可降低盲目探索成本。",
            ],
        }

    def _append_mainline_guidance(self, payload: Dict, state_snapshot: Dict) -> Dict:
        guidance = self._build_mainline_guidance(state_snapshot)
        stage = str(guidance.get("stage", "主线推进"))
        tips = guidance.get("tips", [])
        if not isinstance(tips, list):
            tips = [str(tips)]

        tip_lines = [f"{idx + 1}. {str(t).strip()}" for idx, t in enumerate(tips) if str(t).strip()]
        guidance_block = "\n\n主线推进建议\n" + f"阶段：{stage}\n" + "\n".join(tip_lines)

        narration = str(payload.get("narration", "")).strip()
        if "主线推进建议" not in narration:
            payload["narration"] = (narration + guidance_block).strip()

        payload.setdefault("consistency_notes", [])
        if isinstance(payload["consistency_notes"], list):
            payload["consistency_notes"].append(f"主线阶段: {stage}")
        else:
            payload["consistency_notes"] = [str(payload["consistency_notes"]), f"主线阶段: {stage}"]

        return payload

    @staticmethod
    def _parse_float(value: str) -> float | None:
        try:
            return float(str(value).strip())
        except Exception:
            return None

    @staticmethod
    def _normalize_hold_objects(raw_obj: str) -> List[str]:
        s = str(raw_obj).strip()
        if not s:
            return []

        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    out = [str(x).strip() for x in parsed if str(x).strip()]
                    return out
            except Exception:
                pass
        return [s]

    def _apply_generated_state_changes(self, generated: Dict) -> tuple[List[Fact], List[str]]:
        raw_changes = generated.get("state_changes", [])
        if not raw_changes:
            return [], []

        # 兼容两种格式：
        # 1) 列表：[{subject,predicate,object,operation}]
        # 2) 字典：{"elder": {"friendly_to_player": "55"}}
        if isinstance(raw_changes, dict):
            normalized_changes: List[Dict] = []
            for subject, predicates in raw_changes.items():
                if not isinstance(predicates, dict):
                    continue
                for predicate, value in predicates.items():
                    normalized_changes.append(
                        {
                            "subject": str(subject),
                            "predicate": str(predicate),
                            "object": str(value),
                            "operation": "set",
                        }
                    )
            raw_changes = normalized_changes

        if not isinstance(raw_changes, list):
            return [], []

        applied: List[Fact] = []
        notes: List[str] = []
        turn = max(1, self.state.current_turn)

        for change in raw_changes:
            if not isinstance(change, dict):
                continue

            subject = str(change.get("subject", "")).strip()
            predicate = str(change.get("predicate", "")).strip()
            obj = str(change.get("object", "")).strip()
            operation = str(change.get("operation", "set")).strip().lower()

            if not subject or not predicate:
                continue

            if operation == "set":
                if predicate == "holds":
                    for hold_obj in self._normalize_hold_objects(obj):
                        if not self.state.check_fact_exists(subject, predicate, hold_obj):
                            applied.append(Fact(subject, predicate, hold_obj, turn, True))
                elif obj:
                    applied.append(Fact(subject, predicate, obj, turn, True))
                continue

            if operation == "add":
                # 列表型属性（如 holds）按新增处理。
                if predicate == "holds":
                    for hold_obj in self._normalize_hold_objects(obj):
                        if hold_obj and not self.state.check_fact_exists(subject, predicate, hold_obj):
                            applied.append(Fact(subject, predicate, hold_obj, turn, True))
                    continue

                # 数值型属性按增量处理（如 friendly_to_player: +5）。
                delta = self._parse_float(obj)
                snapshot = self.state.get_current_state(subject)
                current_raw = snapshot.get(subject, {}).get(predicate)
                current_num = self._parse_float(str(current_raw)) if current_raw is not None else None
                if delta is None or current_num is None:
                    if obj:
                        applied.append(Fact(subject, predicate, obj, turn, True))
                    notes.append(f"生成变更回退为覆盖写入: {subject}.{predicate}={obj}")
                    continue

                new_value = current_num + delta
                if float(new_value).is_integer():
                    new_obj = str(int(new_value))
                else:
                    new_obj = f"{new_value:.4f}".rstrip("0").rstrip(".")
                applied.append(Fact(subject, predicate, new_obj, turn, True))
                continue

            if operation == "remove":
                # 当前状态库不支持通用 remove 语义；先跳过并记录。
                notes.append(f"跳过未支持的remove操作: {subject}.{predicate} - {obj}")
                continue

            if obj:
                applied.append(Fact(subject, predicate, obj, turn, True))

        return applied, notes

    @staticmethod
    def _is_relative_location_text(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        markers = ["周围", "四周", "附近", "这里", "原地", "就地", "周边", "前方"]
        return any(m in t for m in markers)

    def _normalize_location_target(self, target: str, current_loc: str, raw_text: str) -> str:
        t = (target or "").strip()
        if not t:
            return current_loc
        if t in self.valid_location_ids:
            return t
        if self._is_relative_location_text(t) or self._is_relative_location_text(raw_text):
            return current_loc
        return t

    def _build_context_options(self, state_snapshot: Dict) -> List[Dict]:
        loc = state_snapshot.get("player", {}).get("location", "village")
        holds = state_snapshot.get("player", {}).get("holds", [])

        base: List[Dict] = []
        if loc == "village":
            if "torch" not in holds:
                base.append({"id": "A", "text": "去前方拿起火把", "intent_hint": "USE_ITEM", "consequence_preview": "提升探索能力"})
            base.append({"id": "B", "text": "与老村长交谈", "intent_hint": "ASK_INFO", "consequence_preview": "获取线索"})
            base.append({"id": "C", "text": "前往森林", "intent_hint": "EXPLORE", "consequence_preview": "接触猎人线"})
            base.append({"id": "D", "text": "深入洞穴", "intent_hint": "EXPLORE", "consequence_preview": "寻找锈剑"})
        elif loc == "forest":
            base = [
                {"id": "A", "text": "与猎人阿洛交谈", "intent_hint": "NEGOTIATE", "consequence_preview": "获取洞穴情报"},
                {"id": "B", "text": "返回村庄", "intent_hint": "EXPLORE", "consequence_preview": "回到安全区"},
                {"id": "C", "text": "前往洞穴", "intent_hint": "EXPLORE", "consequence_preview": "推进主线"},
                {"id": "D", "text": "检查随身物品", "intent_hint": "ASK_INFO", "consequence_preview": "确认资源"},
            ]
        else:
            if "sword" not in holds:
                base.append({"id": "A", "text": "拿起锈剑", "intent_hint": "USE_ITEM", "consequence_preview": "达成关键目标"})
            base.extend(
                [
                    {"id": "B", "text": "继续探索洞穴深处", "intent_hint": "EXPLORE", "consequence_preview": "可能遇到风险"},
                    {"id": "C", "text": "返回村庄", "intent_hint": "EXPLORE", "consequence_preview": "尝试触发结局"},
                    {"id": "D", "text": "整理火把并观察四周", "intent_hint": "ASK_INFO", "consequence_preview": "降低失误"},
                ]
            )

        # 去重并限制到4项
        out: List[Dict] = []
        seen = set()
        for opt in base:
            t = str(opt.get("text", "")).strip()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(opt)
            if len(out) >= 4:
                break

        while len(out) < 4:
            idx = len(out)
            out.append(
                {
                    "id": chr(ord("A") + idx),
                    "text": ["继续探索周边", "与NPC交谈", "检查当前状态", "制定下一步计划"][idx],
                    "intent_hint": "ASK_INFO",
                    "consequence_preview": "稳步推进",
                }
            )
        return out

    def _forbidden_attack_target(self, facts: List[Fact]) -> str | None:
        targets = set(self.story_endings.get("fail", {}).get("forbidden_attack_targets", ["elder"]))
        for fact in facts:
            if fact.subject == "player" and fact.predicate == "attack" and fact.object in targets:
                return fact.object
        return None

    def _is_victory_state(self, state_snapshot: Dict) -> bool:
        victory_cfg = self.story_endings.get("victory", {})
        required_items = victory_cfg.get("required_items", ["sword"])
        return_loc = victory_cfg.get("return_location", "village")

        holds = state_snapshot.get("player", {}).get("holds", [])
        player_loc = state_snapshot.get("player", {}).get("location", "")
        has_items = all(item in holds for item in required_items)
        return has_items and player_loc == return_loc

    def _build_ending_response(self, ending_type: str, state_snapshot: Dict, summary: str) -> Dict:
        ending_texts = {
            "victory": "【结局：守望者归来】你让村庄看到了希望，新的旅程将从此展开。",
            "timeout": "【结局：未竟之夜】故事暂停在篝火熄灭前，命运等待下一次抉择。",
            "bad_forbidden_attack": "【结局：秩序崩坏】你的冲动撕裂了脆弱的同盟。",
        }
        narration = ending_texts.get(ending_type, "【结局】冒险落下帷幕。")
        return {
            "narration": f"{narration}\n\n{summary}",
            "dialogue": None,
            "state_changes": [],
            "next_options": [],
            "consistency_notes": [
                f"终局类型: {ending_type}",
                f"总回合: {self.turn_count}",
                "游戏已结束，输入将不再推进剧情。",
            ],
            "rag_sources": [],
            "game_over": True,
            "ending_type": ending_type,
            "final_state": state_snapshot,
        }

    @staticmethod
    def _render_narration(intent_result: Dict, consistency_result: Dict, state_snapshot: Dict) -> str:
        intent = intent_result.get("intent", "ASK_INFO")
        passed = consistency_result.get("passed", False)

        player_loc = state_snapshot.get("player", {}).get("location", "未知地点")
        if passed:
            return f"你执行了 {intent} 动作。当前你位于 {player_loc}，世界状态已同步更新。"
        return f"你尝试执行 {intent}，但系统检测到潜在冲突，建议调整行动后再尝试。"

    def _build_next_options(self, intent_result: Dict, state_snapshot: Dict) -> List[Dict]:
        _ = intent_result
        return self._build_context_options(state_snapshot)
