# 反馈与动力系统（`feedback-dynamics`）

> 领域：通用。工作结构：`generic_graph`。

```yaml
id: feedback-dynamics
name: 反馈与动力系统
workbench: generic_graph
recognize:
  surface_cues: ["越来越", "恶性循环"]
  structural_checks: ["主要变量和方向能识别"]
  discriminating_test: "外部冲击是否远大于内部反馈？是 → 不确定下的决策"
```

**识别特征**：变量互相影响、随时间演化。

**方法步骤**：

1. 画存量—流量图，标出正负反馈环与延迟
2. 找主导反馈环、不动点与稳定性
3. 找延迟（过冲多由延迟造成）

**合适表示**：因果图（暂用通用图；投资里见 causal-identification）。

**在原问题里怎么验证**：用模型预测下一期方向，到期对照。

**适用假设**：主要变量和方向可识别。

**失效信号**：外部冲击远大于内部反馈。

**常见陷阱**：忽略延迟。

**例子**：价格与基本面的反身性；习惯养成。
