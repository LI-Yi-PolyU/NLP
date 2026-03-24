from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import yaml

from src.core.state_manager import Fact, StateManager


try:
    from transformers import pipeline
except Exception:  # pragma: no cover
    pipeline = None


class ConsistencyChecker:
    def __init__(self, state_manager: StateManager, config_path: str = "config/model_config.yaml"):
        self.state = state_manager

        with open(config_path, "r", encoding="utf-8") as f:
            self.model_config = yaml.safe_load(f) or {}
        with open("config/world_setting.yaml", "r", encoding="utf-8") as f:
            self.world_config = yaml.safe_load(f) or {}

        self.hard_rules = self.world_config.get("rules", {}).get("hard_constraints", [])

        self._connections = {}
        for loc in self.world_config.get("world", {}).get("locations", []):
            self._connections[str(loc.get("id"))] = set(loc.get("connections", []))

        self.nli = None
        nli_model = self.model_config.get("local", {}).get("nli_model")
        if pipeline and nli_model:
            try:
                self.nli = pipeline("text-classification", model=nli_model, device=-1)
            except Exception:
                self.nli = None

    def verify(self, proposed_facts: List[Fact]) -> Dict:
        violations: List[Dict] = []
        context = self._build_runtime_context()

        ordered_facts = sorted(proposed_facts, key=lambda x: (int(x.turn), x.subject, x.predicate))

        for fact in ordered_facts:
            hard_violation = self._check_hard_violation(fact, context)
            if hard_violation:
                violations.append(
                    {
                        "level": "hard",
                        "description": hard_violation,
                        "suggestion": "拒绝此操作",
                    }
                )
            self._apply_fact_to_context(context, fact)

        for fact in ordered_facts:
            conflict = self._check_db_conflict(fact)
            if conflict:
                violations.append(
                    {
                        "level": "db",
                        "description": f"与现有事实冲突: {conflict}",
                        "suggestion": "修正状态或拒绝",
                    }
                )

        if self._needs_semantic_check(proposed_facts):
            semantic_conflict = self._semantic_verification(proposed_facts)
            if semantic_conflict:
                violations.append(
                    {
                        "level": "semantic",
                        "description": semantic_conflict,
                        "suggestion": "修改叙事描述",
                    }
                )

        can_auto_fix = self._attempt_auto_fix(violations)
        fixed_facts = self._build_fixed_facts(proposed_facts, violations) if can_auto_fix else []

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "can_auto_fix": can_auto_fix,
            "fixed_facts": fixed_facts,
        }

    def _check_hard_violation(self, fact: Fact, context: Optional[Dict[str, Dict]] = None) -> Optional[str]:
        runtime = context if context is not None else self._build_runtime_context()

        if "dead_character_cannot_speak" in self.hard_rules:
            status = self._context_get_scalar(runtime, fact.subject, "status")
            if fact.predicate in {"speak", "dialogue"} and status == "dead":
                return f"{fact.subject} 已死亡，不能说话"

        if "item_not_held_cannot_be_used" in self.hard_rules:
            if fact.predicate == "use_item":
                item_id = fact.object
                holds = self._context_get_holds(runtime, "player")
                if item_id not in holds:
                    return f"玩家未持有物品 {item_id}，不能使用"

        if "location_not_connected_cannot_travel" in self.hard_rules:
            if fact.predicate in {"travel", "location"} and fact.subject == "player":
                current_loc = self._context_get_scalar(runtime, "player", "location")
                target = fact.object
                if current_loc and target != current_loc:
                    allowed = self._connections.get(current_loc, set())
                    if target not in allowed:
                        return f"地点 {current_loc} 与 {target} 不连通"

        return None

    def _check_db_conflict(self, fact: Fact) -> Optional[str]:
        if fact.predicate == "location":
            # 合法位置迁移由硬规则（连通性）判定，此处不将“位置变化”视为冲突。
            return None

        if fact.predicate == "status":
            state = self.state.get_current_state(fact.subject)
            old_status = state.get(fact.subject, {}).get("status")
            if old_status and old_status != fact.object and old_status == "dead":
                return f"{fact.subject} 已死亡，状态不可回退为 {fact.object}"

        return None

    @staticmethod
    def _needs_semantic_check(proposed_facts: List[Fact]) -> bool:
        semantic_predicates = {"state_desc", "ability", "condition", "emotion", "action"}
        if any(f.predicate in semantic_predicates for f in proposed_facts):
            return True
        # 当同轮有多条事实时，也启用一次语义层做补充验证。
        return len(proposed_facts) >= 2

    def _semantic_verification(self, proposed_facts: List[Fact]) -> Optional[str]:
        if self.nli is None:
            return None

        pairs = self._build_semantic_pairs(proposed_facts)
        if not pairs:
            return None

        conflicts: List[str] = []
        for premise, hypothesis, description in pairs:
            is_conflict = self._nli_is_contradiction(premise, hypothesis)
            if is_conflict:
                conflicts.append(description)
                if len(conflicts) >= 2:
                    break

        if conflicts:
            return "；".join(conflicts)
        return None

    def _build_semantic_pairs(self, proposed_facts: List[Fact]) -> List[Tuple[str, str, str]]:
        pairs: List[Tuple[str, str, str]] = []
        semantic_predicates = {"status", "condition", "ability", "state_desc", "emotion", "action"}

        # 1) 与当前状态对比（同主体下的语义冲突）
        for fact in proposed_facts:
            if fact.predicate not in semantic_predicates:
                continue
            snapshot = self.state.get_current_state(fact.subject)
            old_state = snapshot.get(fact.subject, {})
            for key, old_value in old_state.items():
                if key not in semantic_predicates:
                    continue
                if str(old_value).strip() == str(fact.object).strip():
                    continue

                premise = f"{fact.subject} 当前{key}是{old_value}。"
                hypothesis = f"{fact.subject} 现在{fact.predicate}是{fact.object}。"
                desc = f"语义冲突：{fact.subject} 的 {key}={old_value} 与 {fact.predicate}={fact.object} 不一致"
                pairs.append((premise, hypothesis, desc))

        # 2) 同轮事实之间的语义冲突
        for i, left in enumerate(proposed_facts):
            if left.predicate not in semantic_predicates:
                continue
            for right in proposed_facts[i + 1 :]:
                if right.subject != left.subject:
                    continue
                if right.predicate not in semantic_predicates:
                    continue
                if left.predicate == right.predicate and left.object == right.object:
                    continue

                premise = f"{left.subject} 的{left.predicate}是{left.object}。"
                hypothesis = f"{right.subject} 的{right.predicate}是{right.object}。"
                desc = (
                    f"语义冲突：同一主体 {left.subject} 在同一回合出现"
                    f" {left.predicate}={left.object} 与 {right.predicate}={right.object}"
                )
                pairs.append((premise, hypothesis, desc))

        return pairs

    def _nli_is_contradiction(self, premise: str, hypothesis: str) -> bool:
        try:
            result = self.nli({"text": premise, "text_pair": hypothesis})
        except Exception:
            try:
                # 兼容部分模型/管线不支持 text_pair 的情况。
                result = self.nli(f"{premise} [SEP] {hypothesis}")
            except Exception:
                return False

        label, score = self._parse_nli_result(result)
        contradiction_labels = {"contradiction", "label_0"}
        return label in contradiction_labels and score >= 0.55

    @staticmethod
    def _parse_nli_result(result) -> Tuple[str, float]:
        if isinstance(result, list) and result:
            row = result[0]
        elif isinstance(result, dict):
            row = result
        else:
            return "", 0.0

        if not isinstance(row, dict):
            return "", 0.0

        label = str(row.get("label", "")).strip().lower()
        try:
            score = float(row.get("score", 0.0))
        except Exception:
            score = 0.0
        return label, score

    def _build_runtime_context(self) -> Dict[str, Dict]:
        snapshot = self.state.get_current_state()
        context: Dict[str, Dict] = {}

        for subject, preds in snapshot.items():
            context[subject] = {}
            if not isinstance(preds, dict):
                continue
            for predicate, obj in preds.items():
                if predicate == "holds":
                    if isinstance(obj, list):
                        context[subject][predicate] = set(str(x) for x in obj)
                    else:
                        context[subject][predicate] = {str(obj)} if str(obj).strip() else set()
                else:
                    context[subject][predicate] = str(obj)

        return context

    @staticmethod
    def _context_get_scalar(context: Dict[str, Dict], subject: str, predicate: str) -> str:
        value = context.get(subject, {}).get(predicate)
        if value is None:
            return ""
        if isinstance(value, set):
            return ""
        return str(value)

    @staticmethod
    def _context_get_holds(context: Dict[str, Dict], subject: str) -> set[str]:
        value = context.get(subject, {}).get("holds", set())
        if isinstance(value, set):
            return value
        if isinstance(value, list):
            return set(str(x) for x in value)
        s = str(value).strip()
        return {s} if s else set()

    def _apply_fact_to_context(self, context: Dict[str, Dict], fact: Fact) -> None:
        context.setdefault(fact.subject, {})
        if fact.predicate == "holds":
            holds = self._context_get_holds(context, fact.subject)
            if fact.object == "none":
                holds.clear()
            elif fact.object:
                holds.add(fact.object)
            context[fact.subject]["holds"] = holds
            return

        if fact.predicate == "travel" and fact.subject == "player" and fact.object:
            context[fact.subject]["location"] = fact.object
            return

        if fact.predicate in {"location", "status", "condition", "ability", "state_desc", "emotion", "action"}:
            context[fact.subject][fact.predicate] = fact.object

    @staticmethod
    def _attempt_auto_fix(violations: List[Dict]) -> bool:
        if not violations:
            return False
        # 仅对“未持有物品却使用”这种硬规则冲突启用自动修复
        return any("未持有物品" in v.get("description", "") for v in violations)

    @staticmethod
    def _build_fixed_facts(proposed_facts: List[Fact], violations: List[Dict]) -> List[Fact]:
        if not any("未持有物品" in v.get("description", "") for v in violations):
            return []

        fixed: List[Fact] = []
        for fact in proposed_facts:
            if fact.predicate == "use_item":
                fixed.append(Fact("player", "action", "fumble_no_item", fact.turn, True))
            else:
                fixed.append(fact)
        return fixed
