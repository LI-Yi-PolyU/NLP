import json
from typing import Any, Dict


VALID_INTENTS = {"EXPLORE", "NEGOTIATE", "ATTACK", "USE_ITEM", "ASK_INFO", "UNKNOWN"}


def _is_valid_entity(entity: Dict[str, Any], text: str) -> bool:
    required = {"type", "value", "start", "end"}
    if not required.issubset(entity):
        return False

    if not isinstance(entity["type"], str) or not isinstance(entity["value"], str):
        return False

    if not isinstance(entity["start"], int) or not isinstance(entity["end"], int):
        return False

    if not (0 <= entity["start"] < entity["end"] <= len(text)):
        return False

    return text[entity["start"] : entity["end"]] == entity["value"]


def validate_intent_data(file_path: str) -> bool:
    """验证JSONL格式正确性，返回是否通过。"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                sample = json.loads(line)
                for key in ("text", "intent", "entities"):
                    if key not in sample:
                        raise ValueError(f"Line {line_no}: missing key '{key}'")

                text = sample["text"]
                intent = sample["intent"]
                entities = sample["entities"]

                if not isinstance(text, str) or not text.strip():
                    raise ValueError(f"Line {line_no}: invalid text")

                if intent not in VALID_INTENTS:
                    raise ValueError(f"Line {line_no}: invalid intent '{intent}'")

                if not isinstance(entities, list):
                    raise ValueError(f"Line {line_no}: entities must be a list")

                for entity in entities:
                    if not isinstance(entity, dict) or not _is_valid_entity(entity, text):
                        raise ValueError(f"Line {line_no}: invalid entity span")

        return True
    except Exception:
        return False
