# StoryWeaver Phase 4 完成说明与使用指南

## 1. 完成结论

Phase 4（演示与界面）已完成，包含：
- 演示控制器（LIVE / SCRIPTED 双模式）
- 状态与调试信息可视化工具
- Gradio 主入口界面
- Trace 导出能力

---

## 2. 对照规格书实现内容

### 2.1 演示控制器

文件：`src/demo/demo_controller.py`

实现项：
- `DemoController` 类
- 双模式：
  - `LIVE`：走真实引擎推理
  - `SCRIPTED`：关键步骤优先走缓存，保证演示稳定
- 缓存加载：`data/benchmarks/demo_scenarios.json`
- 交互日志：`data/benchmarks/demo_trace.jsonl`
- Trace 导出：`export_trace()` 输出 JSON 文件
- 调试视图：`get_debug_view()` 返回意图、状态快照、一致性结果、检索信息

### 2.2 可视化工具

文件：`src/demo/visualizer.py`

实现项：
- `format_state_snapshot(state)`：格式化状态快照
- `format_debug_panel(debug)`：格式化调试面板文本

### 2.3 Gradio 主入口

文件：`app.py`

实现项：
- 初始化 `GameEngine` 与 `DemoController`
- `process_input` 处理用户输入并更新聊天历史
- 展示剧情 + 下一步选项 + 一致性备注
- 调试面板显示内部状态
- 模式切换（LIVE / SCRIPTED）
- Trace 导出按钮
- 支持按钮点击和回车提交

---

## 3. 依赖更新

`requirements.txt` 已新增：
- `gradio>=4.44.0`

---

## 4. 使用方式

### 4.1 安装依赖

```bash
pip install -r requirements.txt
```

### 4.2 启动应用

```bash
python app.py
```

### 4.3 界面操作

1. 在输入框填写行动（如：`我想去forest探索`）
2. 点击“执行”或回车
3. 选择模式：
   - LIVE：实时推理
   - SCRIPTED：演示稳定
4. 勾选“显示调试信息”查看内部状态
5. 点击“导出当前 Trace（用于报告）”导出交互轨迹

---

## 5. 本地验证结果

已验证：
- `DemoController` 可运行，能返回 `narration/next_options`
- `get_debug_view()` 返回关键调试字段
- `export_trace()` 成功导出文件
- `app.py` 可导入且包含 `launch_app()`

---

## 6. 与整体系统的连接关系

- 依赖 Phase 2 的 `GameEngine` 作为推理核心
- 复用 Phase 3 的检索/生成能力（若可用）
- 通过演示层实现“稳定演示 + 可解释调试 + 可导出证据”

这正是答辩场景最需要的一层能力。
