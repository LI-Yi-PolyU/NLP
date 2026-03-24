from __future__ import annotations

import json
import os
from typing import Any, Dict

import yaml
from openai import OpenAI


class APIIntentFallback:
    """当本地NLU置信度较低时调用API。"""

    def __init__(self, config: Dict[str, Any] | None = None, config_path: str = "config/model_config.yaml"):
        if config is None:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        api_cfg = config.get("api", {})
        api_key = os.getenv("DEEP_SEEK_API_KEY", "")
        if not api_key:
            raise ValueError("缺少环境变量 DEEP_SEEK_API_KEY，无法启用 API fallback。")

        self.client = OpenAI(api_key=api_key, base_url=api_cfg.get("base_url"))
        self.model = api_cfg.get("model_nlu_fallback", "deepseek-chat")

    def predict(self, text: str) -> Dict:
        prompt = (
            "分析玩家指令，输出JSON格式。\n"
            "意图选项：EXPLORE, NEGOTIATE, ATTACK, USE_ITEM, ASK_INFO, UNKNOWN\n"
            f"输入：{text}\n"
            "请给出0到1之间的confidence（浮点数，非百分比）。\n"
            "输出：{\"intent\": \"...\", \"confidence\": 0.0, \"entities\": [...], \"reasoning\": \"...\"}"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=300,
        )
        content = response.choices[0].message.content or "{}"

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {"intent": "UNKNOWN", "entities": [], "reasoning": "JSON parse failed"}

        if "intent" not in result:
            result["intent"] = "UNKNOWN"
        if "entities" not in result or not isinstance(result["entities"], list):
            result["entities"] = []

        result["confidence"] = self._normalize_confidence(result.get("confidence"))

        result["source"] = "api_fallback"
        return result

    @staticmethod
    def _normalize_confidence(raw_value: Any) -> float:
        """将模型返回的置信度规范到[0,1]，避免固定0.9带来的伪精度。"""
        try:
            conf = float(raw_value)
        except (TypeError, ValueError):
            return 0.62

        if conf > 1.0:
            conf = conf / 100.0

        conf = max(0.0, min(1.0, conf))
        return round(conf, 6)
