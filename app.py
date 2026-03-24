from __future__ import annotations

import ast
import os
import socket
import threading
import time
from typing import Dict, List

import gradio as gr

from src.core.game_engine import GameEngine
from src.demo.demo_controller import DemoController
from src.demo.visualizer import format_debug_panel

# 初始化引擎（保持原有）
engine = GameEngine()
demo_ctrl = DemoController(engine, mode="LIVE")
_history_lock = threading.RLock()
_persisted_history: List[Dict[str, str]] = []

# ===== 全新视觉设计系统 =====
APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=Inter:wght@400;500;600&display=swap');

:root {
    --bg-dark: #0f172a;
    --bg-card: #1e293b;
    --bg-elevated: #334155;
    --accent-gold: #f59e0b;
    --accent-gold-hover: #d97706;
    --accent-blue: #3b82f6;
    --accent-danger: #ef4444;
    --accent-success: #10b981;
    --text-primary: #f8fafc;
    --text-secondary: #cbd5e1;
    --text-muted: #64748b;
    --border-color: #475569;
    --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2);
    --shadow-lg: 0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
    --radius: 12px;
    --radius-sm: 8px;
}

.gradio-container {
    max-width: none !important;
    width: 100% !important;
    min-height: 100vh !important;
    margin: 0 !important;
    padding: 16px !important;
    box-sizing: border-box;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%) !important;
    font-family: 'Inter', "Noto Serif SC", "Microsoft YaHei", sans-serif;
    color: var(--text-primary);
}

/* 头部标题区 */
.sw-header {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: 24px 32px;
    margin-bottom: 24px;
    box-shadow: var(--shadow-lg);
    position: relative;
    overflow: hidden;
}

.sw-header::before {
    content: "";
    position: absolute;
    right: 24px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 48px;
    opacity: 0.1;
}

.sw-header h1 {
    font-family: 'Noto Serif SC', serif;
    font-size: 32px;
    font-weight: 700;
    color: var(--accent-gold);
    margin: 0 0 8px 0;
    text-shadow: 0 2px 4px rgba(0,0,0,0.5);
}

.sw-header p {
    color: var(--text-secondary);
    margin: 0;
    font-size: 14px;
}

/* 主布局 */
.sw-main-grid {
    display: grid;
    grid-template-columns: 1.2fr 0.8fr;
    gap: 24px;
    align-items: start;
}

/* 叙事区域（左侧） */
.sw-story-panel {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: 20px;
    box-shadow: var(--shadow);
}

/* 聊天记录样式 - 古籍风格 */
.sw-chatbot {
    background: #f8f6f0 !important; /* 羊皮纸色 */
    border: 2px solid #8b7355 !important;
    border-radius: var(--radius) !important;
    font-family: 'Noto Serif SC', serif !important;
    color: #2c1810 !important;
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
}

/* 兼容不同Gradio版本的消息节点，确保文字不会和背景混色 */
.sw-chatbot .message,
.sw-chatbot .message * {
    color: #2c1810 !important;
}

/* 用户输入样式 */
.sw-chatbot .user {
    background: #2c1810 !important;
    color: #f8f6f0 !important;
    border-radius: 12px 12px 0 12px !important;
    border: 1px solid #5c4033 !important;
    font-family: 'Inter', sans-serif !important;
}

.sw-chatbot .user *,
.sw-chatbot [data-testid="user"] .message,
.sw-chatbot [data-testid="user"] .message * {
    color: #f8f6f0 !important;
}

/* AI叙事样式 */
.sw-chatbot .bot {
    background: transparent !important;
    color: #2c1810 !important;
    border-bottom: 1px dashed #8b7355 !important;
    font-family: 'Noto Serif SC', serif !important;
    line-height: 1.8 !important;
}

/* 输入区 */
.sw-input-area {
    background: var(--bg-elevated);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    padding: 12px;
    margin-top: 16px;
    display: flex;
    gap: 12px;
    align-items: center;
}

.sw-input-area input,
.sw-input-area textarea {
    background: var(--bg-dark) !important;
    border: 1px solid var(--border-color) !important;
    color: var(--text-primary) !important;
    border-radius: var(--radius-sm) !important;
    font-size: 16px !important;
}

.sw-input-area input::placeholder,
.sw-input-area textarea::placeholder {
    color: #94a3b8 !important;
    opacity: 1 !important;
}

/* 执行按钮 - 金色主按钮 */
#run-btn {
    flex-shrink: 0;
}

#run-btn button {
    background: linear-gradient(135deg, var(--accent-gold) 0%, var(--accent-gold-hover) 100%) !important;
    color: #0f172a !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    padding: 12px 24px !important;
    font-size: 16px !important;
    box-shadow: 0 4px 6px -1px rgba(245, 158, 11, 0.3) !important;
    transition: all 0.2s ease !important;
    min-width: 100px !important;
}

#run-btn button:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 12px -1px rgba(245, 158, 11, 0.4) !important;
}

/* 状态面板（右侧） - 卡片化 */
.sw-status-panel {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.sw-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: 20px;
    box-shadow: var(--shadow);
    position: relative;
    overflow: hidden;
}

.sw-card::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--accent-gold), var(--accent-blue));
}

.sw-card-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* 状态徽章 */
.sw-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 9999px;
    font-size: 13px;
    font-weight: 600;
    background: var(--bg-elevated);
    color: var(--text-secondary);
    border: 1px solid var(--border-color);
}

.sw-badge.location {
    background: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
    border-color: rgba(59, 130, 246, 0.3);
}

.sw-badge.item {
    background: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    border-color: rgba(245, 158, 11, 0.3);
}

.sw-stage-badge {
    display: inline-flex;
    align-items: center;
    padding: 6px 12px;
    border-radius: 9999px;
    font-size: 13px;
    font-weight: 700;
    border: 1px solid transparent;
}

.sw-stage-prepare {
    background: rgba(14, 165, 233, 0.18);
    color: #7dd3fc;
    border-color: rgba(14, 165, 233, 0.35);
}

.sw-stage-investigate {
    background: rgba(245, 158, 11, 0.18);
    color: #fcd34d;
    border-color: rgba(245, 158, 11, 0.35);
}

.sw-stage-advance {
    background: rgba(16, 185, 129, 0.18);
    color: #6ee7b7;
    border-color: rgba(16, 185, 129, 0.35);
}

.sw-stage-endgame {
    background: rgba(249, 115, 22, 0.18);
    color: #fdba74;
    border-color: rgba(249, 115, 22, 0.35);
}

.sw-stage-finish {
    background: rgba(168, 85, 247, 0.18);
    color: #d8b4fe;
    border-color: rgba(168, 85, 247, 0.35);
}

.sw-stage-default {
    background: rgba(148, 163, 184, 0.18);
    color: #cbd5e1;
    border-color: rgba(148, 163, 184, 0.35);
}

/* 回合计数器 - 突出显示 */
.sw-turn-counter {
    background: linear-gradient(135deg, var(--accent-blue) 0%, #2563eb 100%);
    color: white;
    padding: 8px 16px;
    border-radius: var(--radius-sm);
    font-weight: 700;
    text-align: center;
    font-size: 18px;
    box-shadow: 0 4px 6px -1px rgba(59, 130, 246, 0.3);
}

/* 游戏结束状态 */
.sw-game-over {
    background: linear-gradient(135deg, var(--accent-danger) 0%, #dc2626 100%) !important;
    color: white !important;
    padding: 12px;
    border-radius: var(--radius-sm);
    text-align: center;
    font-weight: 700;
    animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: .7; }
}

/* JSON状态树美化 */
.sw-json-tree {
    background: var(--bg-dark) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-secondary) !important;
    font-family: 'Monaco', 'Consolas', monospace !important;
    font-size: 12px !important;
    line-height: 1.5 !important;
}

/* 调试面板 - 科技风 */
.sw-debug {
    background: #020617 !important;
    border: 1px solid #1e293b !important;
    color: #22c55e !important;
    font-family: 'Monaco', monospace !important;
    font-size: 11px !important;
    line-height: 1.6 !important;
    padding: 12px !important;
    border-radius: var(--radius-sm) !important;
}

/* 模式切换 - 分段控制器风格 */
.sw-mode-toggle .wrap {
    background: var(--bg-elevated) !important;
    border-radius: var(--radius-sm) !important;
    padding: 4px !important;
}

.sw-mode-toggle label {
    background: transparent !important;
    color: var(--text-secondary) !important;
    border-radius: 6px !important;
    transition: all 0.2s !important;
}

.sw-mode-toggle label.selected {
    background: var(--accent-blue) !important;
    color: white !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

/* 延迟指示器 */
.sw-latency {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--text-muted);
}

.sw-latency.good { color: var(--accent-success); }
.sw-latency.warning { color: var(--accent-gold); }
.sw-latency.bad { color: var(--accent-danger); }

/* 导出按钮 */
.sw-export-btn button {
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border-color) !important;
    color: var(--text-secondary) !important;
    font-size: 12px !important;
}

/* 响应式 */
@media (max-width: 1024px) {
    .gradio-container {
        padding: 10px !important;
    }

    .sw-header {
        padding: 16px;
    }

    .sw-header h1 {
        font-size: 24px;
    }

    .sw-input-area {
        flex-direction: column;
        align-items: stretch;
    }

    #run-btn button {
        width: 100% !important;
        min-width: 0 !important;
    }
}
"""

def _opening_background_text() -> str:
    return (
        "**青石村 · 禁忌洞穴探险**\n\n"
        "你站在村庄中央的石板路上，晨雾中传来远处洞穴的低语。\n"
        "老村长握着锈迹斑斑的钥匙，猎人阿洛在酒馆擦拭弓箭。\n\n"
        "**任务目标**：调查洞穴传闻，获取关键物品，安全返回。\n"
        "**时间限制**：有限回合内完成，否则夜幕降临...\n\n"
        "*提示：输入行动如「探索周围」「与老村长交谈」「前往洞穴」*"
    )


def _initial_chat_history() -> List[Dict[str, str]]:
    return [{"role": "assistant", "content": _opening_background_text()}]


def _get_persisted_history() -> List[Dict[str, str]]:
    with _history_lock:
        if _persisted_history:
            return [dict(x) for x in _persisted_history]
    return _initial_chat_history()


def _set_persisted_history(history: List[Dict[str, str]]) -> None:
    with _history_lock:
        _persisted_history.clear()
        _persisted_history.extend([dict(x) for x in history])


def _render_story(result: dict) -> str:
    """优化后的故事渲染，支持Markdown格式"""
    lines = []
    
    # 游戏结束标题
    if result.get("game_over"):
        lines.append("## 游戏结束\n")
    
    # 叙事内容
    narration = result.get("narration", "")
    if narration:
        lines.append(f"{narration}\n")
    
    # 对话（特殊样式）
    dialogue = result.get("dialogue")
    if isinstance(dialogue, dict) and dialogue:
        speaker = dialogue.get('speaker', 'NPC')
        content = dialogue.get('content', '')
        lines.append(f"> **{speaker}**：*{content}*\n")
    elif isinstance(dialogue, str) and dialogue.strip():
        lines.append(f"> **神秘声音**：*{dialogue.strip()}*\n")
    
    # 选项（按钮式展示）
    options = result.get("next_options", [])
    if isinstance(options, list) and options:
        lines.append("---\n**可选行动：**")
        for idx, opt in enumerate(options):
            if isinstance(opt, dict):
                hint = opt.get("consequence_preview") or opt.get("consequence_hint", "")
                suffix = f" *({hint})*" if hint else ""
                opt_id = opt.get("id", chr(ord("A") + idx))
                opt_text = opt.get("text", "继续")
                lines.append(f"\n**{opt_id}.** {opt_text}{suffix}")
        lines.append("\n")
    
    # 系统备注（折叠式）
    notes = result.get("consistency_notes", [])
    if isinstance(notes, str):
        notes = [notes]
    if isinstance(notes, list) and notes:
        lines.append("<details><summary>系统处理详情（点击展开）</summary>\n")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("</details>")
    
    return "\n".join(lines)


def _render_status_badges(debug: dict) -> tuple:
    """渲染状态徽章HTML"""
    snapshot = debug.get("fact_db_snapshot", {}) if isinstance(debug, dict) else {}
    player = snapshot.get("player", {}) if isinstance(snapshot, dict) else {}
    
    location = str(player.get("location", "未知"))
    holds = _normalize_holds(player.get("holds", []))
    
    # 位置徽章
    location_html = f'<span class="sw-badge location">{location}</span>'
    
    # 物品徽章组
    if holds:
        items_html = " ".join([f'<span class="sw-badge item">{item}</span>' for item in holds])
    else:
        items_html = '<span class="sw-badge">空</span>'
    
    return location_html, items_html


def _render_debug_info(debug_mode: bool, mode: str, latency_ms: float = 0) -> str:
    if debug_mode:
        debug = demo_ctrl.get_debug_view() or {}
        return format_debug_panel(debug)
    
    # 简洁模式
    debug = demo_ctrl.get_debug_view() or {}
    intent = debug.get("current_intent", {}) or {}
    consistency = debug.get("consistency_check_result", {}) or {}
    
    intent_name = intent.get("intent", "UNKNOWN")
    confidence = float(intent.get("confidence", 0.0) or 0.0)
    passed = bool(consistency.get("passed", True))
    
    status_icon = "通过" if passed else "未通过"
    conf_color = "good" if confidence > 0.8 else "warning" if confidence > 0.5 else "bad"
    
    return f"""
<div class="sw-latency {conf_color}">
    <span>延迟 {latency_ms:.0f}ms</span> | 
    <span>意图 {intent_name} ({confidence:.0%})</span> | 
    <span>一致性 {status_icon}</span> | 
    <span>模式 {mode}</span>
</div>
"""


def _build_state_panel(debug: dict) -> Dict:
    """构建右侧状态面板数据"""
    snapshot = debug.get("fact_db_snapshot", {}) if isinstance(debug, dict) else {}
    player = snapshot.get("player", {}) if isinstance(snapshot, dict) else {}
    
    location = str(player.get("location", "未知地点"))
    holds = _normalize_holds(player.get("holds", []))
    
    turn_count = int(getattr(demo_ctrl.engine, "turn_count", 0) or 0)
    game_over = bool(getattr(demo_ctrl.engine, "game_over", False))
    ending_type = (getattr(demo_ctrl.engine, "ending_payload", {}) or {}).get("ending_type", "")
    
    # 游戏状态文本
    if game_over:
        status_text = f"**已结束** - {ending_type or '未知结局'}"
        status_class = "sw-game-over"
    else:
        status_text = "进行中"
        status_class = ""

    mainline_stage = _compute_mainline_stage(snapshot)
    
    return {
        "location_badge": location,
        "inventory_list": "、".join([f"{h}" for h in holds]) if holds else "（空）",
        "turn": turn_count,
        "mainline_stage": _render_mainline_stage_badge(mainline_stage),
        "status": status_text,
        "status_class": status_class,
        "raw_state": snapshot,
    }


def _normalize_holds(raw_holds) -> List[str]:
    """将可能被字符串化的列表物品展开，避免出现 ['torch'] 这类嵌套展示。"""
    if isinstance(raw_holds, list):
        source = raw_holds
    elif raw_holds is None:
        source = []
    else:
        source = [raw_holds]

    flat: List[str] = []
    for item in source:
        if isinstance(item, list):
            flat.extend([str(x).strip() for x in item if str(x).strip()])
            continue

        s = str(item).strip()
        if not s:
            continue

        # 兼容历史脏数据："['torch']" / "[\"torch\", \"sword\"]"
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    flat.extend([str(x).strip() for x in parsed if str(x).strip()])
                    continue
            except Exception:
                pass

        flat.append(s)

    deduped: List[str] = []
    seen = set()
    for x in flat:
        if x in seen:
            continue
        seen.add(x)
        deduped.append(x)
    return deduped


def _compute_mainline_stage(snapshot: Dict) -> str:
    player = snapshot.get("player", {}) if isinstance(snapshot, dict) else {}
    loc = str(player.get("location", "village"))
    holds = _normalize_holds(player.get("holds", []))
    hold_set = set(str(x) for x in holds)

    if "sword" in hold_set and loc == "village":
        return "主线收束阶段：可触发结局"
    if "torch" not in hold_set:
        return "准备阶段：先获取火把"
    if loc == "village":
        return "调查阶段：与长老/猎人确认洞穴线索"
    if loc == "forest":
        return "推进阶段：获取洞穴情报并前往洞穴"
    if loc == "cave":
        if "sword" in hold_set:
            return "撤离阶段：返回村庄完成主线"
        return "终盘阶段：优先找到并拿起锈剑"
    return "探索阶段"


def _stream_chunks(text: str, chunk_size: int = 36):
    t = str(text or "")
    if not t:
        yield ""
        return
    for idx in range(chunk_size, len(t) + chunk_size, chunk_size):
        yield t[:idx]


def _render_mainline_stage_badge(stage_text: str) -> str:
    t = str(stage_text or "探索阶段").strip()
    if "准备阶段" in t:
        cls = "sw-stage-prepare"
    elif "调查阶段" in t:
        cls = "sw-stage-investigate"
    elif "推进阶段" in t:
        cls = "sw-stage-advance"
    elif "终盘阶段" in t or "撤离阶段" in t:
        cls = "sw-stage-endgame"
    elif "收束阶段" in t:
        cls = "sw-stage-finish"
    else:
        cls = "sw-stage-default"
    return f'<span class="sw-stage-badge {cls}">{t}</span>'


def process_input(user_input: str, history: List[Dict[str, str]], debug_mode: bool, mode: str):
    history = history or _get_persisted_history()
    user_input = (user_input or "").strip()
    start_time = time.perf_counter()
    
    if not user_input:
        debug = demo_ctrl.get_debug_view() or {}
        panel = _build_state_panel(debug)
        latency = (time.perf_counter() - start_time) * 1000.0

        yield (
            history,
            _render_debug_info(debug_mode, mode, latency),
            "",
            panel["location_badge"],
            panel["inventory_list"],
            f"第 {panel['turn']} 回合",
            panel["mainline_stage"],
            panel["status"],
            panel["status_class"],
            panel["raw_state"],
            latency,
        )
        return
    
    demo_ctrl.mode = (mode or "LIVE").upper()
    
    # 计算回合数
    current_step = sum(1 for m in history if isinstance(m, dict) and m.get("role") == "assistant")
    if history and isinstance(history[0], dict):
        first_content = str(history[0].get("content", ""))
        if history[0].get("role") == "assistant" and "青石村" in first_content:
            current_step = max(0, current_step - 1)

    user_turn = {"role": "user", "content": f"**行动**：{user_input}"}
    thinking_turn = {"role": "assistant", "content": "正在生成中，请稍候..."}
    warmup_history = history + [user_turn, thinking_turn]
    _set_persisted_history(warmup_history)

    warmup_debug = demo_ctrl.get_debug_view() or {}
    warmup_panel = _build_state_panel(warmup_debug)
    yield (
        warmup_history,
        _render_debug_info(debug_mode, mode, 0.0),
        "",
        warmup_panel["location_badge"],
        warmup_panel["inventory_list"],
        f"第 {warmup_panel['turn']} 回合",
        warmup_panel["mainline_stage"],
        warmup_panel["status"],
        warmup_panel["status_class"],
        warmup_panel["raw_state"],
        0.0,
    )
    
    try:
        result = demo_ctrl.process_turn(user_input, current_step)
        response_text = _render_story(result)
    except Exception as exc:
        response_text = f"**系统异常**：{exc}\n\n请尝试重新输入或切换至 SCRIPTED 模式。"

    # 构建输出
    debug = demo_ctrl.get_debug_view() or {}
    panel = _build_state_panel(debug)
    latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
    debug_info = _render_debug_info(debug_mode, mode, latency_ms)

    for partial in _stream_chunks(response_text):
        partial_history = history + [user_turn, {"role": "assistant", "content": partial}]
        _set_persisted_history(partial_history)
        yield (
            partial_history,
            debug_info,
            "",
            panel["location_badge"],
            panel["inventory_list"],
            f"第 {panel['turn']} 回合",
            panel["mainline_stage"],
            panel["status"],
            panel["status_class"],
            panel["raw_state"],
            latency_ms,
        )

    return


def export_trace():
    try:
        export_path = demo_ctrl.export_trace()
        return f"已导出至：`{export_path}`"
    except Exception as e:
        return f"❌ 导出失败：{e}"


def initialize_ui(debug_mode: bool, mode: str):
    debug = demo_ctrl.get_debug_view() or {}
    panel = _build_state_panel(debug)
    
    return (
        _get_persisted_history(),
        _render_debug_info(debug_mode, mode, 0),
        panel["location_badge"],
        panel["inventory_list"],
        f"第 {panel['turn']} 回合",
        panel["mainline_stage"],
        panel["status"],
        panel["status_class"],
        panel["raw_state"],
        0.0,
    )


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _pick_server_port() -> int:
    for port in range(7860, 7901):
        if _is_port_free(port):
            return port
    raise RuntimeError("端口 7860-7900 均被占用")


def launch_app():
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

    with gr.Blocks(title="StoryWeaver - AI文本冒险", css=APP_CSS) as demo:
        # 头部
        gr.HTML("""
            <div class="sw-header">
                <h1>StoryWeaver</h1>
                <p>基于深度状态管理的动态叙事系统 | DeepSeek驱动生成 | 实时一致性校验</p>
            </div>
        """)
        
        with gr.Row(equal_height=True):
            # ===== 左侧：叙事区域 =====
            with gr.Column(scale=3):
                # 聊天记录（使用自定义CSS类）
                chatbot = gr.Chatbot(
                    label="冒险日志",
                    height=520,
                    value=_get_persisted_history(),
                    elem_classes=["sw-chatbot"],
                )
                
                # 输入区（美化）
                with gr.Row(elem_classes=["sw-input-area"]):
                    msg = gr.Textbox(
                        label="",
                        placeholder="输入行动指令... 例如：「探索前方洞穴」或「与老村长交谈」",
                        scale=8,
                        show_label=False,
                    )
                    run_btn = gr.Button("▶ 执行", scale=1, elem_id="run-btn")
                
                # 快捷操作示例
                with gr.Row():
                    gr.Examples(
                        examples=[
                            ["查看周围环境"],
                            ["与老村长交谈"],
                            ["前往禁忌洞穴"],
                            ["检查背包物品"],
                        ],
                        inputs=msg,
                        label="快捷指令",
                        examples_per_page=4,
                    )
            
            # ===== 右侧：状态面板 =====
            with gr.Column(scale=2, elem_classes=["sw-status-panel"]):
                
                # 回合计数器
                turn_display = gr.Markdown(
                    value="第 0 回合",
                    elem_classes=["sw-turn-counter"]
                )
                
                # 位置状态卡
                with gr.Group(elem_classes=["sw-card"]):
                    gr.Markdown('<div class="sw-card-title">当前位置</div>')
                    location_badge = gr.Markdown(value="青石村")
                
                # 物品栏卡
                with gr.Group(elem_classes=["sw-card"]):
                    gr.Markdown('<div class="sw-card-title">携带物品</div>')
                    inventory_box = gr.Markdown(value="（空）")

                # 主线阶段卡
                with gr.Group(elem_classes=["sw-card"]):
                    gr.Markdown('<div class="sw-card-title">主线阶段</div>')
                    mainline_stage_box = gr.Markdown(value=_render_mainline_stage_badge("准备阶段：先获取火把"))
                
                # 游戏状态卡
                with gr.Group(elem_classes=["sw-card"]):
                    gr.Markdown('<div class="sw-card-title">游戏状态</div>')
                    status_md = gr.Markdown(value="进行中")
                    status_class = gr.Textbox(visible=False)  # 用于传递CSS类
                
                # 调试与配置（可折叠）
                with gr.Accordion("系统配置与调试", open=False):
                    mode_radio = gr.Radio(
                        choices=["LIVE", "SCRIPTED"],
                        value="LIVE",
                        label="演示模式",
                        info="LIVE: 实时AI生成 | SCRIPTED: 预置缓存（极速）",
                        elem_classes=["sw-mode-toggle"],
                    )
                    
                    debug_toggle = gr.Checkbox(
                        label="显示完整调试信息",
                        value=False,
                    )
                    
                    debug_box = gr.Textbox(
                        label="系统内部状态",
                        lines=8,
                        elem_classes=["sw-debug"],
                    )
                    
                    latency_box = gr.Number(
                        label="响应延迟 (ms)",
                        value=0.0,
                        precision=1,
                        interactive=False,
                    )
                    
                    export_btn = gr.Button("导出当前Trace", size="sm", elem_classes=["sw-export-btn"])
                    export_info = gr.Textbox(label="导出结果", lines=1, interactive=False)
                
                # 原始JSON（折叠）
                with gr.Accordion("原始状态数据", open=False):
                    state_json = gr.JSON(
                        label="Fact Database Snapshot",
                        elem_classes=["sw-json-tree"],
                    )
        
        # 事件绑定
        run_btn.click(
            process_input,
            [msg, chatbot, debug_toggle, mode_radio],
            [chatbot, debug_box, msg, location_badge, inventory_box, turn_display, mainline_stage_box, status_md, status_class, state_json, latency_box],
        )
        msg.submit(
            process_input,
            [msg, chatbot, debug_toggle, mode_radio],
            [chatbot, debug_box, msg, location_badge, inventory_box, turn_display, mainline_stage_box, status_md, status_class, state_json, latency_box],
        )
        
        demo.load(
            initialize_ui,
            [debug_toggle, mode_radio],
            [chatbot, debug_box, location_badge, inventory_box, turn_display, mainline_stage_box, status_md, status_class, state_json, latency_box],
        )
        
        debug_toggle.change(
            lambda d, m: _render_debug_info(d, m, 0),
            [debug_toggle, mode_radio],
            [debug_box],
        )
        
        export_btn.click(export_trace, [], [export_info])

    server_port = _pick_server_port()
    print(f"[StoryWeaver] 启动于 http://127.0.0.1:{server_port}")
    demo.launch(server_name="127.0.0.1", server_port=server_port)


if __name__ == "__main__":
    launch_app()