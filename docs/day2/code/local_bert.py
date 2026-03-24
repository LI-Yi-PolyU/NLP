from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from src.nlu.entity_extractor import RuleBasedEntityExtractor


try:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
except Exception:  # pragma: no cover
    torch = None
    AutoModelForSequenceClassification = None
    AutoTokenizer = None


class LocalIntentClassifier:
    """本地意图分类器。优先使用 Transformer，失败时回退关键词规则。"""

    def __init__(self, config_path: str = "config/model_config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f) or {}

        bert_model = self.config.get("local", {}).get("bert_model", "distilbert-base-uncased")
        self.intent_map = {
            0: "EXPLORE",
            1: "NEGOTIATE",
            2: "ATTACK",
            3: "USE_ITEM",
            4: "ASK_INFO",
        }

        self.tokenizer = None
        self.model = None
        if AutoTokenizer and AutoModelForSequenceClassification:
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(bert_model, local_files_only=True)
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    bert_model,
                    num_labels=5,
                    local_files_only=True,
                )
            except Exception:
                self.tokenizer = None
                self.model = None

        self.vectorizer = None
        self.linear_model = None
        self.linear_labels: List[str] = []
        self._init_linear_classifier()

        self.extractor = RuleBasedEntityExtractor()

    def predict(self, text: str) -> Dict:
        entities = self._extract_entities(text)

        linear_intent, linear_conf = self._linear_predict(text)
        if linear_intent:
            if linear_conf >= 0.55:
                return {
                    "intent": linear_intent,
                    "confidence": linear_conf,
                    "entities": entities,
                    "source": "local_linear",
                }

            # 线性模型低置信时，优先输出 UNKNOWN，避免把噪声误判成可执行意图。
            keyword_intent, keyword_conf = self._keyword_predict(text)
            if linear_intent == "UNKNOWN" and keyword_intent == "UNKNOWN":
                return {
                    "intent": "UNKNOWN",
                    "confidence": max(linear_conf, keyword_conf),
                    "entities": entities,
                    "source": "local_linear_unknown",
                }

        if self.tokenizer is None or self.model is None or torch is None:
            intent, confidence = self._keyword_predict(text)
            return {
                "intent": intent,
                "confidence": confidence,
                "entities": entities,
                "source": "keyword_fallback",
            }

        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)
            confidence, predicted_class = torch.max(probs, dim=-1)

        intent = self.intent_map[predicted_class.item()]
        conf = float(confidence.item())

        # 预训练分类头未微调时可能不稳定，用关键词做轻量矫正
        if conf < 0.35:
            intent, conf = self._keyword_predict(text)
            source = "keyword_override"
        else:
            source = "local_bert"

        return {
            "intent": intent,
            "confidence": conf,
            "entities": entities,
            "source": source,
        }

    def _init_linear_classifier(self, train_path: str = "data/benchmarks/intent_train.jsonl") -> None:
        fp = Path(train_path)
        if not fp.exists():
            return

        texts: List[str] = []
        labels: List[str] = []

        try:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    text = str(row.get("text", "")).strip()
                    label = str(row.get("intent", "")).strip()
                    if not text or not label:
                        continue
                    texts.append(text)
                    labels.append(label)
        except Exception:
            return

        if len(set(labels)) < 2 or len(texts) < 20:
            return

        try:
            vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3), min_df=1)
            x = vectorizer.fit_transform(texts)
            model = LogisticRegression(max_iter=500, class_weight="balanced")
            model.fit(x, labels)

            self.vectorizer = vectorizer
            self.linear_model = model
            self.linear_labels = [str(x) for x in model.classes_]
        except Exception:
            self.vectorizer = None
            self.linear_model = None
            self.linear_labels = []

    def _linear_predict(self, text: str) -> Tuple[str, float]:
        if self.vectorizer is None or self.linear_model is None:
            return "", 0.0
        t = (text or "").strip()
        if not t:
            return "", 0.0
        try:
            x = self.vectorizer.transform([t])
            probs = self.linear_model.predict_proba(x)[0]
            idx = int(probs.argmax())
            intent = str(self.linear_model.classes_[idx])
            conf = float(probs[idx])
            return intent, round(conf, 6)
        except Exception:
            return "", 0.0

    def _extract_entities(self, text: str) -> List[Dict]:
        return self.extractor.extract(text)

    @staticmethod
    def _keyword_predict(text: str) -> tuple[str, float]:
        t = text.lower()

        explore_kw = ["去", "前往", "探索", "看看", "移动", "travel", "explore"]
        negotiate_kw = ["谈", "协商", "交易", "说服", "negotiat", "talk"]
        attack_kw = ["攻击", "砍", "打", "战斗", "attack", "fight"]
        use_item_kw = ["使用", "拿", "装备", "点亮", "use", "equip"]
        ask_kw = ["问", "打听", "信息", "线索", "ask", "info"]

        intent_keywords: List[Tuple[str, List[str]]] = [
            ("EXPLORE", explore_kw),
            ("NEGOTIATE", negotiate_kw),
            ("ATTACK", attack_kw),
            ("USE_ITEM", use_item_kw),
            ("ASK_INFO", ask_kw),
        ]

        best_intent = "ASK_INFO"
        best_hits = 0
        for intent_name, keywords in intent_keywords:
            hit_count = sum(1 for k in keywords if k and k in t)
            if hit_count > best_hits:
                best_intent = intent_name
                best_hits = hit_count

        if best_hits <= 0:
            return "UNKNOWN", 0.45

        # 命中词越多，置信度越高；避免长期固定在0.8/0.9
        conf = min(0.95, 0.56 + 0.09 * best_hits)
        return best_intent, round(conf, 6)
