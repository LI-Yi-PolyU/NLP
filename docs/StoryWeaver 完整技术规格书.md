# StoryWeaver 完整技术规格书（Vibe Coding版）
**目标**：构建基于AI的文本冒险游戏，支持动态剧情生成、状态一致性维护、自动化评估  
**技术约束**：单人开发、4周交付、混合架构（本地NLP+API生成）、零人工标注数据  
**评分目标**：14.5/15%（顶级档）

---

## 一、文件结构（必须严格遵循）

```text
storyweaver/
├── config/
│   ├── world_setting.yaml          # 世界观定义
│   ├── model_config.yaml           # API密钥与模型参数
│   └── prompts/
│       ├── intent_classification.txt
│       ├── story_generation.json   # JSON Schema约束
│       └── consistency_rules.yaml  # 硬规则定义
├── data/
│   ├── raw_corpus/                 # 原始语料（空文件夹，后续爬取）
│   ├── benchmarks/
│   │   ├── intent_train.jsonl      # 500条（自动生成的训练集）
│   │   ├── intent_test.jsonl       # 100条（测试集）
│   │   ├── consistency_test.jsonl  # 200组（对抗样本）
│   │   └── demo_scenarios.json     # 3条演讲路径（预置状态序列）
│   └── vector_index/               # FAISS索引文件
├── src/
│   ├── __init__.py
│   ├── nlu/
│   │   ├── __init__.py
│   │   ├── local_bert.py           # 本地意图分类
│   │   ├── api_fallback.py         # API疑难处理
│   │   └── entity_extractor.py     # 实体抽取
│   ├── core/
│   │   ├── __init__.py
│   │   ├── state_manager.py        # SQLite状态管理
│   │   ├── consistency_checker.py  # 三层一致性检测
│   │   └── game_engine.py          # 主协调器
│   ├── generation/
│   │   ├── __init__.py
│   │   ├── retriever.py            # RAG检索
│   │   └── story_gen.py            # API故事生成
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── metrics.py              # 指标计算
│   │   └── auto_eval.py            # 批量评估
│   └── demo/
│       ├── visualizer.py           # 状态可视化
│       └── demo_controller.py      # 演讲模式控制
├── app.py                          # Gradio界面（主入口）
├── run_data_pipeline.py            # 一键数据生成
├── run_evaluation.py             # 一键评估
├── requirements.txt
└── README.md
```

---

## 二、Phase by Phase 实施指令

### Phase 1: 基础设施与数据流水线（Week 1）
**目标**：生成所有必要数据，建立评估基准，无需人工标注

#### Step 1.1: 配置文件模板
创建 `config/world_setting.yaml`：
```yaml
world:
  setting: " medieval_fantasy"  # 背景设定
  locations:
    - id: "village"
      name: "青石村"
      danger_level: 0
      connections: ["forest", "cave"]
    - id: "cave"
      name: "禁忌洞穴"
      danger_level: 3
  
  characters:
    - id: "elder"
      name: "老村长"
      location: "village"
      status: "alive"
      friendly_to_player: 50  # 0-100
  
  items:
    - id: "sword"
      name: "锈剑"
      location: "cave"
      holder: null  # null表示在场景中

rules:
  hard_constraints:
    - "dead_character_cannot_speak"
    - "item_not_held_cannot_be_used"
    - "location_not_connected_cannot_travel"
```

创建 `config/model_config.yaml`：
```yaml
api:
  openai_api_key: ""  # 用户填写
  base_url: "https://api.openai.com/v1"
  model_nlu_fallback: "gpt-4o-mini"
  model_generation: "gpt-4o-mini"
  temperature: 0.7
  max_tokens: 512

local:
  bert_model: "distilbert-base-uncased"  # 先用英文，中文可换bert-base-chinese
  nli_model: "facebook/bart-large-mnli"
  embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
```

#### Step 1.2: 自动化数据生成脚本
创建 `run_data_pipeline.py`，实现以下函数：

```python
# 函数签名必须严格匹配
def generate_intent_dataset(n_train=400, n_test=100, output_dir="data/benchmarks") -> None:
    """
    基于world_setting中的实体，合成意图识别数据集
    意图类型：EXPLORE, NEGOTIATE, ATTACK, USE_ITEM, ASK_INFO
    
    输出格式（JSONL）：
    {"text": "我想去森林看看", "intent": "EXPLORE", "entities": [{"type": "location", "value": "forest"}], "confidence_score": 1.0}
    
    实现逻辑：
    1. 加载world_setting中的locations/characters/items
    2. 为每个意图类型定义模板（如EXPLORE: ["去{location}", "探索{location}", "前往{location}"]）
    3. 填充实体生成具体句子
    4. 添加10%噪声样本（随机打乱实体，意图设为UNKNOWN）
    5. 划分train/test，保存为jsonl
    """
    pass

def generate_consistency_benchmark(n_pairs=200, output_path="data/benchmarks/consistency_test.jsonl") -> None:
    """
    基于硬规则生成对抗样本对（一致 vs 矛盾）
    
    输出格式：
    {"facts": ["玩家持有剑", "玩家用剑战斗"], "label": "CONSISTENT", "rule_type": "item_usage"}
    {"facts": ["村长已死亡", "村长说话"], "label": "CONFLICT", "rule_type": "dead_speak"}
    
    实现逻辑：
    1. 定义矛盾模板（见world_setting.rules.hard_constraints）
    2. 随机选择实体实例化模板
    3. 生成50%一致对（正确状态转移），50%矛盾对
    """
    pass

def build_rag_corpus(output_dir="data/raw_corpus") -> None:
    """
    构建RAG语料库（先合成300条高质量场景，后续可爬取补充）
    每个场景包含：setting, characters, plot_summary, text_segment
    
    使用API生成高质量叙事片段（一次性调用，成本<$2）
    """
    pass

if __name__ == "__main__":
    generate_intent_dataset()
    generate_consistency_benchmark()
    build_rag_corpus()
    print("数据流水线完成")
```

#### Step 1.3: 数据格式验证
创建 `src/data_validator.py`：
```python
def validate_intent_data(file_path: str) -> bool:
    """验证JSONL格式正确性，返回是否通过"""
    pass
```

---

### Phase 2: 核心NLP管道（Week 2）
**目标**：实现NLU→State→Consistency→Generation的端到端流程

#### Step 2.1: 本地NLU模块
`src/nlu/local_bert.py`：
```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import yaml

class LocalIntentClassifier:
    def __init__(self, config_path="config/model_config.yaml"):
        # 加载配置
        # 使用distilbert-base-uncased（或中文bert）
        # num_labels = 5 (EXPLORE, NEGOTIATE, ATTACK, USE_ITEM, ASK_INFO)
        self.tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
        self.model = AutoModelForSequenceClassification.from_pretrained(
            "distilbert-base-uncased", 
            num_labels=5
        )
        self.intent_map = {0: "EXPLORE", 1: "NEGOTIATE", 2: "ATTACK", 3: "USE_ITEM", 4: "ASK_INFO"}
        
    def predict(self, text: str) -> dict:
        """
        返回: {
            "intent": str,
            "confidence": float,
            "entities": list  # 简单的正则/规则提取，如"去{location}"中的location
        }
        """
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)
            confidence, predicted_class = torch.max(probs, dim=-1)
        
        return {
            "intent": self.intent_map[predicted_class.item()],
            "confidence": confidence.item(),
            "entities": self._extract_entities(text)  # 简单规则实现
        }
    
    def _extract_entities(self, text: str) -> list:
        # 基于world_setting中的实体名做字符串匹配
        pass
```

`src/nlu/api_fallback.py`：
```python
import openai

class APIIntentFallback:
    """当本地BERT置信度<0.7时调用"""
    def __init__(self, config):
        self.client = openai.OpenAI(api_key=config["api"]["openai_api_key"])
        self.model = config["api"]["model_nlu_fallback"]
    
    def predict(self, text: str) -> dict:
        prompt = f"""分析玩家指令，输出JSON格式。
        意图选项：EXPLORE, NEGOTIATE, ATTACK, USE_ITEM, ASK_INFO, UNKNOWN
        输入：{text}
        输出：{{"intent": "...", "entities": [...], "reasoning": "..."}}"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
```

#### Step 2.2: 状态管理器（关键模块）
`src/core/state_manager.py`：
```python
import sqlite3
from dataclasses import dataclass
from typing import List, Dict
import yaml

@dataclass
class Fact:
    subject: str      # 实体ID，如"player", "elder"
    predicate: str    # 关系，如"location", "holds", "status"
    object: str       # 值，如"village", "sword", "dead"
    turn: int         # 时间戳（第几轮）
    valid: bool       # 是否有效（支持临时状态）

class StateManager:
    def __init__(self, db_path="data/state.db"):
        self.conn = sqlite3.connect(db_path)
        self._init_db()
        self.current_turn = 0
        
    def _init_db(self):
        """初始化表结构"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY,
                subject TEXT,
                predicate TEXT,
                object TEXT,
                turn INTEGER,
                valid BOOLEAN DEFAULT 1,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()
    
    def get_current_state(self, subject: str = None) -> Dict:
        """
        获取当前状态快照
        如果subject=None，返回整个世界状态（用于生成提示）
        返回格式：{
            "player": {"location": "village", "holds": ["bread"]},
            "elder": {"location": "village", "status": "alive", "friendly": 50}
        }
        """
        pass
    
    def update_state(self, facts: List[Fact]) -> None:
        """批量插入新事实，标记旧事实为invalid（如果需要覆盖）"""
        pass
    
    def check_fact_exists(self, subject: str, predicate: str, object: str) -> bool:
        """查询特定事实是否存在且有效"""
        pass
```

#### Step 2.3: 三层一致性检查器
`src/core/consistency_checker.py`：
```python
from transformers import pipeline
import yaml

class ConsistencyChecker:
    def __init__(self, state_manager, config_path="config/model_config.yaml"):
        self.state = state_manager
        self.config = yaml.safe_load(open(config_path))
        
        # 加载硬规则（从world_setting.yaml）
        self.hard_rules = self.config["rules"]["hard_constraints"]
        
        # 加载本地NLI模型（语义冲突检测）
        self.nli = pipeline("text-classification", 
                           model=self.config["local"]["nli_model"],
                           device=-1)  # CPU
        
    def verify(self, proposed_facts: List[Fact]) -> Dict:
        """
        三层验证：
        1. Hard Rules：符号逻辑检查（如死亡检测）
        2. DB Check：与现有事实冲突（如位置矛盾）
        3. Semantic：语义推理（如"虚弱"vs"举重物"）
        
        返回: {
            "passed": bool,
            "violations": [{"level": "hard/db/semantic", "description": str, "suggestion": str}],
            "can_auto_fix": bool,
            "fixed_facts": List[Fact]  # 如果可以自动修复
        }
        """
        violations = []
        
        # 层1：硬规则
        for fact in proposed_facts:
            if self._check_hard_violation(fact):
                violations.append({
                    "level": "hard",
                    "description": f"违反硬规则: {fact}",
                    "suggestion": "拒绝此操作"
                })
        
        # 层2：数据库事实核对
        for fact in proposed_facts:
            conflict = self._check_db_conflict(fact)
            if conflict:
                violations.append({
                    "level": "db",
                    "description": f"与现有事实冲突: {conflict}",
                    "suggestion": "修正状态或拒绝"
                })
        
        # 层3：语义检查（仅对复杂描述启用）
        if self._needs_semantic_check(proposed_facts):
            semantic_conflict = self._semantic_verification(proposed_facts)
            if semantic_conflict:
                violations.append({
                    "level": "semantic",
                    "description": semantic_conflict,
                    "suggestion": "修改叙事描述"
                })
        
        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "can_auto_fix": self._attempt_auto_fix(violations),
            "fixed_facts": []  # 如果修复成功，填充此字段
        }
    
    def _check_hard_violation(self, fact: Fact) -> bool:
        # 实现具体规则检查，如 fact.predicate=="speak" and 查询得fact.subject已死亡
        pass
    
    def _attempt_auto_fix(self, violations: List[Dict]) -> bool:
        # 尝试自动修复，如检测到"未持有却使用"→自动改为"你伸手摸空，发现物品不在"
        pass
```

---

### Phase 3: 生成与评估（Week 3）

#### Step 3.1: RAG检索器
`src/generation/retriever.py`：
```python
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import json

class NarrativeRetriever:
    def __init__(self, corpus_path="data/raw_corpus", index_path="data/vector_index"):
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
        self.index = self._load_or_build_index(corpus_path, index_path)
        
    def _load_or_build_index(self, corpus_path, index_path):
        # 加载或构建FAISS索引
        pass
    
    def retrieve(self, query: str, current_location: str, k=3) -> List[Dict]:
        """
        检索相似场景作为Few-shot示例
        query格式: "{intent} at {location}"
        返回: [{"scenario": str, "similarity": float}]
        """
        pass
```

#### Step 3.2: API故事生成器
`src/generation/story_gen.py`：
```python
import openai
import json
from typing import Dict, List

class StoryGenerator:
    def __init__(self, config, retriever, state_manager):
        self.client = openai.OpenAI(api_key=config["api"]["openai_api_key"])
        self.model = config["api"]["model_generation"]
        self.retriever = retriever
        self.state = state_manager
        
    def generate(self, intent_result: Dict, state_snapshot: Dict) -> Dict:
        """
        生成故事片段，必须输出结构化JSON
        
        输入：
            intent_result: {"intent": "EXPLORE", "entities": [...]}
            state_snapshot: 当前世界状态字典
        输出：
            {
                "narration": "你走进洞穴，黑暗中传来低语...",
                "dialogue": null or {"speaker": "村长", "content": "..."},
                "state_changes": [{"subject": "player", "predicate": "location", "object": "cave"}],
                "next_options": [
                    {"id": "A", "text": "点亮火把", "consequence_hint": "可能发现物品"},
                    {"id": "B", "text": "大声回应", "consequence_hint": "风险：暴露位置"}
                ],
                "consistency_notes": ["自动修正：原输入尝试使用未持有物品，已改为摸索动作"]
            }
        """
        # 1. RAG检索
        retrieved = self.retriever.retrieve(
            f"{intent_result['intent']} at {state_snapshot['player']['location']}",
            state_snapshot['player']['location']
        )
        
        # 2. 构建系统提示（包含世界观、状态、约束、示例）
        system_prompt = self._build_system_prompt(state_snapshot, retrieved)
        
        # 3. 用户提示（玩家意图）
        user_prompt = f"玩家意图：{intent_result}\n当前状态：{json.dumps(state_snapshot, ensure_ascii=False)}"
        
        # 4. 调用API，强制JSON输出
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={
                "type": "json_schema",
                "schema": self._get_output_schema()  # 定义严格的JSON结构
            },
            temperature=0.7,
            max_tokens=600
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # 5. 后处理：验证返回的state_changes是否与fact_database逻辑一致
        return self._validate_output(result, state_snapshot)
    
    def _build_system_prompt(self, state, retrieved_scenarios) -> str:
        # 组装包含世界观、约束、RAG示例的提示
        base = open("config/prompts/story_generation.json").read()
        # 填充具体内容...
        return base
```

#### Step 3.3: 自动化评估器
`src/evaluation/auto_eval.py`：
```python
from sklearn.metrics import f1_score, accuracy_score
import time
import json

class AutoEvaluator:
    def __init__(self, nlu_engine, consistency_checker, state_manager):
        self.nlu = nlu_engine
        self.checker = consistency_checker
        self.state = state_manager
        
    def run_full_evaluation(self, output_path="evaluation_report.json"):
        """运行完整评估，生成报告"""
        results = {
            "intent_recognition": self._eval_intent(),
            "consistency_detection": self._eval_consistency(),
            "generation_latency": self._eval_latency(),
            "branch_diversity": self._eval_diversity()
        }
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        return results
    
    def _eval_intent(self) -> Dict:
        """在intent_test.jsonl上评估准确率"""
        # 加载data/benchmarks/intent_test.jsonl
        # 对比predict vs label
        # 返回 {"accuracy": float, "f1_macro": float, "per_class_f1": dict}
        pass
    
    def _eval_consistency(self) -> Dict:
        """在consistency_test.jsonl上评估检测准确率"""
        pass
    
    def _eval_latency(self) -> Dict:
        """测试100轮平均延迟"""
        pass
    
    def _eval_diversity(self) -> Dict:
        """测试分支多样性（生成10个不同选择的故事，计算文本相似度）"""
        pass
```

---

### Phase 4: 演示与界面（Week 4）

#### Step 4.1: 演示控制器（稳定性保障）
`src/demo/demo_controller.py`：
```python
import json
import hashlib

class DemoController:
    """
    双模式演示系统：
    - LIVE: 真实API调用（展示实时性）
    - SCRIPTED: 预缓存响应（确保稳定性）
    """
    def __init__(self, game_engine, mode="LIVE"):
        self.engine = game_engine
        self.mode = mode
        self.cache = self._load_cache()
        
    def _load_cache(self):
        # 加载data/benchmarks/demo_scenarios.json作为缓存
        pass
    
    def process_turn(self, user_input: str, current_step: int) -> Dict:
        if self.mode == "SCRIPTED" and self._in_critical_path(current_step):
            return self._get_cached_response(current_step)
        
        # LIVE模式或常规路径
        try:
            result = self.engine.process_turn(user_input)
            self._log_interaction(current_step, user_input, result)
            return result
        except Exception as e:
            if self.mode == "SCRIPTED":
                return self._get_fallback_response(current_step)
            raise e
    
    def get_debug_view(self) -> Dict:
        """获取系统内部状态用于演讲展示"""
        return {
            "current_intent": self.engine.last_intent,
            "fact_db_snapshot": self.engine.state.get_current_state(),
            "consistency_check_result": self.engine.last_consistency_result,
            "rag_retrieved_items": self.engine.last_retrieved_scenarios
        }
```

#### Step 4.2: Gradio界面
`app.py`（主入口）：
```python
import gradio as gr
from src.core.game_engine import GameEngine
from src.demo.demo_controller import DemoController

# 初始化
engine = GameEngine()
demo_ctrl = DemoController(engine, mode="LIVE")

def process_input(user_input, history, debug_mode):
    result = demo_ctrl.process_turn(user_input, len(history))
    
    # 组装显示文本
    story_text = result["narration"]
    if result.get("dialogue"):
        story_text += f"\n\n{result['dialogue']['speaker']}: {result['dialogue']['content']}"
    
    options = result.get("next_options", [])
    options_text = "\n".join([f"{opt['id']}. {opt['text']}" for opt in options])
    
    # 调试信息（演讲时展示）
    debug_info = ""
    if debug_mode:
        debug = demo_ctrl.get_debug_view()
        debug_info = f"""
        [系统内部状态]
        识别意图: {debug['current_intent']}
        一致性检查: {debug['consistency_check_result']['passed']}
        检索到相似场景: {len(debug['rag_retrieved_items'])}个
        """
    
    return story_text + "\n\n" + options_text, debug_info

with gr.Blocks() as demo:
    gr.Markdown("# StoryWeaver - AI文本冒险游戏")
    
    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(label="剧情")
            msg = gr.Textbox(label="你的行动")
            btn = gr.Button("执行")
        
        with gr.Column(scale=1):
            debug_box = gr.Textbox(label="系统调试信息（演讲模式）", lines=10)
            debug_toggle = gr.Checkbox(label="显示调试信息", value=False)
            export_btn = gr.Button("导出当前Trace（用于报告）")
    
    btn.click(process_input, [msg, chatbot, debug_toggle], [chatbot, debug_box])
    
demo.launch()
```

---

## 三、关键数据格式规范（JSON Schema）

### 1. 意图数据格式
```json
{
  "text": "我想去森林探索",
  "intent": "EXPLORE",
  "entities": [
    {"type": "location", "value": "forest", "start": 3, "end": 5}
  ],
  "metadata": {
    "source": "synthetic",
    "difficulty": "easy"
  }
}
```

### 2. 一致性测试格式
```json
{
  "facts": [
    {"subject": "player", "predicate": "location", "object": "village", "turn": 1},
    {"subject": "player", "predicate": "location", "object": "cave", "turn": 2}
  ],
  "expected_label": "CONFLICT",
  "rule_violated": "location_teleport_without_travel",
  "description": "玩家没有旅行动作却瞬间移动"
}
```

### 3. 游戏引擎输出格式（必须严格遵循）
```json
{
  "narration": "string",           // 第三人称叙述
  "dialogue": {                     // 可选
    "speaker": "string",
    "content": "string",
    "emotion": "string"             // 可选，用于展示
  },
  "state_changes": [                // 明确的状态变更提议
    {
      "subject": "string",
      "predicate": "string",        // location/holds/status/relationship
      "object": "string",
      "operation": "set/add/remove"
    }
  ],
  "next_options": [                 // 下一步选项（必须有）
    {
      "id": "A/B/C",
      "text": "string",             // 显示文本
      "intent_hint": "string",      // 对应意图类型（用于NLU辅助）
      "consequence_preview": "string"  // 结果预览（如"危险"）
    }
  ],
  "consistency_notes": ["string"],  // 一致性修正记录（演讲亮点）
  "rag_sources": ["string"]         // 检索到的来源ID（可解释性）
}
```

---

评分标准：

**1. 适当性（Appropriateness）（3%）：**

- 任务设定、挑战、方法论和系统功能高度适当且相关。（3%）
- 任务设定、挑战、方法论和系统功能大部分适当且相关。（2.5%）
- 任务设定、挑战、方法论和系统功能表现出一定程度的适当性。（2%）
- 任务设定、挑战、方法论和系统功能不充分。（1.5%）
- 任务设定、挑战、方法论和系统功能不适当。（1%）

**2. 严谨性（Soundness）（3%）：**

- 项目展示全面且组织良好的开发过程，解释清晰且逻辑清楚。（3%）
- 项目展示大部分全面且组织良好的开发过程，解释大部分清晰且逻辑清楚。（2.5%）
- 项目展示一定程度的组织和逻辑，但解释有些不清楚。（2%）
- 项目展示有限的组织和逻辑，解释不充分。（1.5%）
- 项目组织混乱，缺乏清晰或逻辑的开发过程，解释不清楚或不合逻辑。（1%）

**3. 吸引力（Excitement）（3%）：**

- 项目呈现创新且引人入胜的想法，始终能吸引观众的注意力。（3%）
- 项目呈现引人入胜的想法，大部分能吸引观众的注意力，但可能缺乏一致性。（2.5%）
- 项目呈现一定程度的吸引力，但有改进空间且观众注意力 inconsistent。（2%）
- 项目缺乏创新，无法持续激发观众的兴趣。（1.5%）
- 项目缺乏吸引力或无法吸引观众。（1%）

**4. 演讲表现（Presentation）（3%）：**

- 演讲高度精致且专业，表达出色，视觉辅助工具使用有效。（3%）
- 演讲大部分精致且专业，表达良好，视觉辅助工具使用充分。（2.5%）
- 演讲在精致度和专业性方面有一些改进空间，表达可能缺乏一致性。（2%）
- 演讲缺乏精致度和专业性，表达薄弱，视觉辅助工具无效。（1.5%）
- 演讲执行不佳，难以理解，视觉辅助工具使用无效。（1%）

**5. 写作（Writing）（3%）：**

- 项目报告写作精良，解释清晰简洁，语法和格式使用正确。（3%）

- 项目报告大部分写作良好，解释大部分清晰简洁，语法和格式使用大部分正确。（2.5%）
- 项目报告写作尚可，但存在一些清晰度问题和语法格式使用不一致。（2%）
- 项目报告写作较差，解释不清楚或令人困惑，语法和格式存在重大错误。（1.5%）
- 项目报告写作非常差，存在大量清晰度和格式错误，难以理解。（1%）