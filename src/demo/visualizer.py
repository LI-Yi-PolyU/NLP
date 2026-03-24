from __future__ import annotations

import json
from typing import Dict


def format_state_snapshot(state: Dict) -> str:
    """将状态字典格式化为便于演示阅读的文本。"""
    if not state:
        return "<empty state>"
    return json.dumps(state, ensure_ascii=False, indent=2)


def format_debug_panel(debug: Dict) -> str:
    """将调试视图转为可直接展示的字符串。"""
    current_intent = debug.get("current_intent")
    consistency = debug.get("consistency_check_result") or {}
    rag_items = debug.get("rag_retrieved_items") or []

    return (
        f"模式: {debug.get('mode', 'UNKNOWN')}\n"
        f"识别意图: {json.dumps(current_intent, ensure_ascii=False)}\n"
        f"一致性通过: {consistency.get('passed')}\n"
        f"冲突数量: {len(consistency.get('violations', []))}\n"
        f"检索到相似场景: {len(rag_items)}\n"
        f"Trace文件: {debug.get('trace_file', '')}\n"
    )
