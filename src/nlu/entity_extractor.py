from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import yaml


@dataclass
class EntityCandidate:
    entity_type: str
    value: str


class RuleBasedEntityExtractor:
    """基于世界配置中的实体名和ID做字符串匹配。"""

    def __init__(self, world_config_path: str = "config/world_setting.yaml") -> None:
        with open(world_config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        world = cfg.get("world", {})

        self._entities: List[EntityCandidate] = []
        for loc in world.get("locations", []):
            self._entities.append(EntityCandidate("location", str(loc.get("id", ""))))
            if loc.get("name"):
                self._entities.append(EntityCandidate("location", str(loc["name"])))

        for ch in world.get("characters", []):
            self._entities.append(EntityCandidate("character", str(ch.get("id", ""))))
            if ch.get("name"):
                self._entities.append(EntityCandidate("character", str(ch["name"])))

        for item in world.get("items", []):
            self._entities.append(EntityCandidate("item", str(item.get("id", ""))))
            if item.get("name"):
                self._entities.append(EntityCandidate("item", str(item["name"])))

        # 长词优先，避免短词先匹配导致跨度错误
        self._entities.sort(key=lambda x: len(x.value), reverse=True)

    def extract(self, text: str) -> List[Dict]:
        entities: List[Dict] = []
        used_spans: List[tuple[int, int]] = []

        for cand in self._entities:
            if not cand.value:
                continue
            start = text.find(cand.value)
            if start < 0:
                continue
            end = start + len(cand.value)

            overlap = any(not (end <= s or start >= e) for s, e in used_spans)
            if overlap:
                continue

            used_spans.append((start, end))
            entities.append(
                {
                    "type": cand.entity_type,
                    "value": cand.value,
                    "start": start,
                    "end": end,
                }
            )

        return entities
