import json
import os
import random
from pathlib import Path
from typing import Dict, List, Optional

import yaml

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


INTENTS = ["EXPLORE", "NEGOTIATE", "ATTACK", "USE_ITEM", "ASK_INFO"]


def _ensure_dir(path: str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_world_setting(config_path: str = "config/world_setting.yaml") -> Dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_model_config(config_path: str = "config/model_config.yaml") -> Dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _find_span(text: str, value: str) -> Optional[Dict[str, int]]:
    start = text.find(value)
    if start == -1:
        return None
    return {"start": start, "end": start + len(value)}


def _sample_template(intent: str, location: str, character: str, item: str) -> str:
    templates = {
        "EXPLORE": ["我想去{location}看看", "前往{location}", "探索一下{location}"],
        "NEGOTIATE": ["我想和{character}谈谈", "和{character}协商", "请求{character}帮忙"],
        "ATTACK": ["我攻击{character}", "对{character}发动进攻", "用力砍向{character}"],
        "USE_ITEM": ["我使用{item}", "拿{item}来处理", "试着用{item}"],
        "ASK_INFO": ["向{character}打听消息", "问{character}关于{location}的事", "请{character}解释线索"],
    }

    template = random.choice(templates[intent])
    return template.format(location=location, character=character, item=item)


def _extract_entities(text: str, location: str, character: str, item: str) -> List[Dict]:
    entities: List[Dict] = []
    candidates = [
        ("location", location),
        ("character", character),
        ("item", item),
    ]
    for ent_type, value in candidates:
        span = _find_span(text, value)
        if span:
            entities.append({"type": ent_type, "value": value, **span})
    return entities


def generate_intent_dataset(n_train=500, n_test=100, output_dir="data/benchmarks") -> None:
    """
    基于world_setting中的实体，合成意图识别数据集。
    """
    random.seed(42)
    world = _load_world_setting()["world"]

    locations = [x["id"] for x in world.get("locations", [])] + [x["name"] for x in world.get("locations", [])]
    characters = [x["id"] for x in world.get("characters", [])] + [x["name"] for x in world.get("characters", [])]
    items = [x["id"] for x in world.get("items", [])] + [x["name"] for x in world.get("items", [])]

    total = n_train + n_test
    noise_count = max(1, int(total * 0.1))
    clean_count = total - noise_count

    samples: List[Dict] = []

    for i in range(clean_count):
        intent = INTENTS[i % len(INTENTS)]
        location = random.choice(locations)
        character = random.choice(characters)
        item = random.choice(items)

        text = _sample_template(intent, location, character, item)
        entities = _extract_entities(text, location, character, item)
        samples.append(
            {
                "text": text,
                "intent": intent,
                "entities": entities,
                "confidence_score": 1.0,
                "metadata": {"source": "synthetic", "difficulty": "easy"},
            }
        )

    # 10% 噪声样本: 实体与句子语义错配，意图置为 UNKNOWN
    noise_templates = [
        "现在立刻把{location}吃掉",
        "和{item}谈判并搬走{character}",
        "请把{character}塞进{location}",
    ]
    for _ in range(noise_count):
        location = random.choice(locations)
        character = random.choice(characters)
        item = random.choice(items)
        text = random.choice(noise_templates).format(location=location, character=character, item=item)
        entities = _extract_entities(text, location, character, item)
        samples.append(
            {
                "text": text,
                "intent": "UNKNOWN",
                "entities": entities,
                "confidence_score": 0.4,
                "metadata": {"source": "synthetic_noise", "difficulty": "hard"},
            }
        )

    random.shuffle(samples)
    train_data = samples[:n_train]
    test_data = samples[n_train : n_train + n_test]

    out_dir = _ensure_dir(output_dir)
    train_path = out_dir / "intent_train.jsonl"
    test_path = out_dir / "intent_test.jsonl"

    with open(train_path, "w", encoding="utf-8") as f:
        for row in train_data:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with open(test_path, "w", encoding="utf-8") as f:
        for row in test_data:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def generate_consistency_benchmark(n_pairs=200, output_path="data/benchmarks/consistency_test.jsonl") -> None:
    """
    基于硬规则生成对抗样本对（一致 vs 矛盾）。
    """
    random.seed(43)
    world_cfg = _load_world_setting()
    world = world_cfg["world"]
    rules = world_cfg.get("rules", {}).get("hard_constraints", [])

    locations = [x["id"] for x in world.get("locations", [])]
    characters = [x["id"] for x in world.get("characters", [])]
    items = [x["id"] for x in world.get("items", [])]

    def make_pair(rule: str, conflict: bool) -> Dict:
        if rule == "dead_character_cannot_speak":
            c = random.choice(characters)
            if conflict:
                facts = [
                    {"subject": c, "predicate": "status", "object": "dead", "turn": 1},
                    {"subject": c, "predicate": "speak", "object": "yes", "turn": 2},
                ]
                label = "CONFLICT"
            else:
                facts = [
                    {"subject": c, "predicate": "status", "object": "alive", "turn": 1},
                    {"subject": c, "predicate": "speak", "object": "yes", "turn": 2},
                ]
                label = "CONSISTENT"
            rule_name = "dead_character_cannot_speak"

        elif rule == "item_not_held_cannot_be_used":
            i = random.choice(items)
            if conflict:
                facts = [
                    {"subject": "player", "predicate": "holds", "object": "none", "turn": 1},
                    {"subject": "player", "predicate": "use_item", "object": i, "turn": 2},
                ]
                label = "CONFLICT"
            else:
                facts = [
                    {"subject": "player", "predicate": "holds", "object": i, "turn": 1},
                    {"subject": "player", "predicate": "use_item", "object": i, "turn": 2},
                ]
                label = "CONSISTENT"
            rule_name = "item_not_held_cannot_be_used"

        else:
            src = random.choice(locations)
            dst = random.choice([x for x in locations if x != src])
            connected = []
            for loc in world.get("locations", []):
                if loc.get("id") == src:
                    connected = loc.get("connections", [])
                    break

            is_connected = dst in connected
            if conflict and is_connected:
                dst = "forbidden_castle"
                is_connected = False

            if conflict and not is_connected:
                facts = [
                    {"subject": "player", "predicate": "location", "object": src, "turn": 1},
                    {"subject": "player", "predicate": "travel", "object": dst, "turn": 2},
                ]
                label = "CONFLICT"
            else:
                if not is_connected:
                    valid_choices = connected or [src]
                    dst = random.choice(valid_choices)
                facts = [
                    {"subject": "player", "predicate": "location", "object": src, "turn": 1},
                    {"subject": "player", "predicate": "travel", "object": dst, "turn": 2},
                ]
                label = "CONSISTENT"
            rule_name = "location_not_connected_cannot_travel"

        return {
            "facts": facts,
            "label": label,
            "expected_label": label,
            "rule_type": rule_name,
            "rule_violated": rule_name if label == "CONFLICT" else "none",
        }

    out = []
    half = n_pairs // 2
    for i in range(n_pairs):
        conflict = i < half
        rule = random.choice(rules or [
            "dead_character_cannot_speak",
            "item_not_held_cannot_be_used",
            "location_not_connected_cannot_travel",
        ])
        out.append(make_pair(rule, conflict))

    random.shuffle(out)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_rag_corpus(output_dir="data/raw_corpus") -> None:
    """
    构建RAG语料库（默认合成300条，若配置了API Key则可扩展为API生成）。
    """
    random.seed(44)
    world = _load_world_setting()["world"]
    model_cfg = _load_model_config()

    out_dir = _ensure_dir(output_dir)
    corpus_file = out_dir / "synthetic_scenarios.jsonl"

    locations = world.get("locations", [])
    characters = world.get("characters", [])
    items = world.get("items", [])

    def _template_scene(idx: int, source: str = "template") -> Dict:
        loc = random.choice(locations)
        ch = random.choice(characters)
        item = random.choice(items)
        mood = random.choice(["紧张", "神秘", "希望", "压抑", "温暖"])
        return {
            "id": f"scene_{idx:04d}",
            "setting": world.get("setting", "medieval_fantasy"),
            "location": loc.get("id", "unknown"),
            "characters": [ch.get("id", "unknown")],
            "plot_summary": f"玩家在{loc.get('name', loc.get('id'))}与{ch.get('name', ch.get('id'))}互动，围绕{item.get('name', item.get('id'))}展开抉择。",
            "text_segment": (
                f"{loc.get('name', loc.get('id'))}的风带着{mood}气息。"
                f"{ch.get('name', ch.get('id'))}低声提起{item.get('name', item.get('id'))}的传闻，"
                "并提醒玩家每一次选择都可能重写村庄的命运。"
            ),
            "source": source,
        }

    def _strip_json_fence(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return text

    api_key = os.getenv("DEEP_SEEK_API_KEY", "")
    api_base_url = model_cfg.get("api", {}).get("base_url") or None
    rows: List[Dict] = []

    if api_key and OpenAI is not None:
        try:
            client = OpenAI(api_key=api_key, base_url=api_base_url)
            total_target = 60
            batch_size = 20
            api_scene_idx = 0
            while api_scene_idx < total_target:
                try:
                    current_batch = min(batch_size, total_target - api_scene_idx)
                    prompt = {
                        "setting": world.get("setting", "medieval_fantasy"),
                        "locations": [x.get("id") for x in locations],
                        "characters": [x.get("id") for x in characters],
                        "items": [x.get("id") for x in items],
                        "task": (
                            f"生成{current_batch}条高质量文本冒险场景，输出JSON对象："
                            "{\"scenes\":[...]}，每条包含location, character, item, plot_summary, text_segment。"
                        ),
                    }
                    response = client.chat.completions.create(
                        model=model_cfg.get("api", {}).get("model_generation", "gpt-4o-mini"),
                        messages=[
                            {"role": "system", "content": "你是叙事设计师，只输出合法JSON。"},
                            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.7,
                        max_tokens=2200,
                    )
                    content = _strip_json_fence(response.choices[0].message.content or "{}")
                    parsed = json.loads(content)

                    api_scenes = parsed.get("scenes", [])
                    if not isinstance(api_scenes, list):
                        api_scenes = []

                    if not api_scenes:
                        break

                    for scene in api_scenes:
                        rows.append(
                            {
                                "id": f"scene_{len(rows):04d}",
                                "setting": world.get("setting", "medieval_fantasy"),
                                "location": scene.get("location", random.choice(locations).get("id", "unknown")),
                                "characters": [scene.get("character", random.choice(characters).get("id", "unknown"))],
                                "plot_summary": scene.get("plot_summary", "玩家遭遇新的选择。"),
                                "text_segment": scene.get("text_segment", "风声掠过古老石墙，未知在前方等待。"),
                                "source": "api",
                            }
                        )
                    api_scene_idx = len(rows)
                except Exception as batch_exc:
                    print(f"[WARN] API 批次生成失败，保留已生成片段。原因: {batch_exc}")
                    break
        except Exception as exc:
            print(f"[WARN] API 客户端初始化失败，回退模板生成。原因: {exc}")

    while len(rows) < 300:
        rows.append(_template_scene(len(rows), source="template"))

    with open(corpus_file, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_demo_scenarios(output_path="data/benchmarks/demo_scenarios.json") -> None:
    scenarios = [
        {
            "id": "demo_path_safe",
            "steps": [
                {"input": "前往village", "expected_intent": "EXPLORE"},
                {"input": "和elder谈谈", "expected_intent": "NEGOTIATE"},
                {"input": "问elder关于cave", "expected_intent": "ASK_INFO"},
            ],
        },
        {
            "id": "demo_path_risky",
            "steps": [
                {"input": "前往cave", "expected_intent": "EXPLORE"},
                {"input": "使用torch", "expected_intent": "USE_ITEM"},
                {"input": "攻击hunter", "expected_intent": "ATTACK"},
            ],
        },
        {
            "id": "demo_path_tradeoff",
            "steps": [
                {"input": "前往forest", "expected_intent": "EXPLORE"},
                {"input": "和hunter协商", "expected_intent": "NEGOTIATE"},
                {"input": "使用sword", "expected_intent": "USE_ITEM"},
            ],
        },
    ]
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    generate_intent_dataset()
    generate_consistency_benchmark()
    build_rag_corpus()
    _build_demo_scenarios()
    print("数据流水线完成")
