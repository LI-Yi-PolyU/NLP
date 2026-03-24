from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import yaml


@dataclass
class Fact:
    subject: str
    predicate: str
    object: str
    turn: int
    valid: bool = True


class StateManager:
    def __init__(self, db_path: str = "data/state.db", world_config_path: str = "config/world_setting.yaml"):
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(db_file), check_same_thread=False)
        self.world_config_path = world_config_path
        self._init_db()
        self.current_turn = self._load_current_turn()
        self._bootstrap_world_state(world_config_path)

    def _init_db(self):
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY,
                    subject TEXT,
                    predicate TEXT,
                    object TEXT,
                    turn INTEGER,
                    valid BOOLEAN DEFAULT 1,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_facts_subject_pred ON facts(subject, predicate)")
            self.conn.commit()

    def _load_current_turn(self) -> int:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(turn), 0) FROM facts")
            row = cursor.fetchone()
        return int(row[0] or 0)

    def _bootstrap_world_state(self, world_config_path: str) -> None:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(1) FROM facts")
            count = cursor.fetchone()[0]
        if count > 0:
            return

        with open(world_config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        world = cfg.get("world", {})

        seed_facts: List[Fact] = [Fact("player", "location", "village", 0)]

        for ch in world.get("characters", []):
            cid = str(ch.get("id"))
            if ch.get("location"):
                seed_facts.append(Fact(cid, "location", str(ch["location"]), 0))
            if ch.get("status"):
                seed_facts.append(Fact(cid, "status", str(ch["status"]), 0))
            if ch.get("friendly_to_player") is not None:
                seed_facts.append(Fact(cid, "friendly_to_player", str(ch["friendly_to_player"]), 0))

        for item in world.get("items", []):
            iid = str(item.get("id"))
            holder = item.get("holder")
            if holder:
                seed_facts.append(Fact(str(holder), "holds", iid, 0))
            elif item.get("location"):
                seed_facts.append(Fact(iid, "location", str(item["location"]), 0))

        self.update_state(seed_facts)

    def reset_world_state(self) -> None:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM facts")
            self.conn.commit()
            self.current_turn = 0

        self._bootstrap_world_state(self.world_config_path)

    def get_current_state(self, subject: str = None) -> Dict:
        with self._lock:
            cursor = self.conn.cursor()

            if subject:
                cursor.execute(
                    """
                    SELECT subject, predicate, object, turn
                    FROM facts
                    WHERE valid = 1 AND subject = ?
                    ORDER BY turn ASC, id ASC
                    """,
                    (subject,),
                )
            else:
                cursor.execute(
                    """
                    SELECT subject, predicate, object, turn
                    FROM facts
                    WHERE valid = 1
                    ORDER BY turn ASC, id ASC
                    """
                )

            rows = cursor.fetchall()
        snapshot: Dict[str, Dict] = {}

        for sub, pred, obj, _turn in rows:
            if sub not in snapshot:
                snapshot[sub] = {}

            if pred == "holds":
                snapshot[sub].setdefault("holds", [])
                if obj not in snapshot[sub]["holds"]:
                    snapshot[sub]["holds"].append(obj)
            else:
                snapshot[sub][pred] = obj

        return snapshot

    def update_state(self, facts: List[Fact]) -> None:
        if not facts:
            return

        with self._lock:
            cursor = self.conn.cursor()
            single_value_predicates = {"location", "status", "friendly_to_player", "relationship"}

            for fact in facts:
                if fact.predicate in single_value_predicates:
                    cursor.execute(
                        """
                        UPDATE facts
                        SET valid = 0
                        WHERE subject = ? AND predicate = ? AND valid = 1
                        """,
                        (fact.subject, fact.predicate),
                    )

                cursor.execute(
                    """
                    INSERT INTO facts(subject, predicate, object, turn, valid)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (fact.subject, fact.predicate, fact.object, fact.turn, int(fact.valid)),
                )
                self.current_turn = max(self.current_turn, fact.turn)

            self.conn.commit()

    def check_fact_exists(self, subject: str, predicate: str, object: str) -> bool:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT 1
                FROM facts
                WHERE subject = ? AND predicate = ? AND object = ? AND valid = 1
                LIMIT 1
                """,
                (subject, predicate, object),
            )
            return cursor.fetchone() is not None
