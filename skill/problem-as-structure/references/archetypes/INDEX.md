# 母题索引

识别结构（阶段 ②）时先读这张表，挑 1–3 个候选，再读选中的文件。每个文件的格式相同：识别（表面线索、结构检查、区分检验）、方法步骤、工作结构、原问题里的验证、假设、失效信号、陷阱、例子。

| 母题 | 文件 | 领域 | 识别特征 | 工作结构 |
|---|---|---|---|---|
| 约束满足与可达性 | `constraint-satisfaction.md` | 通用 | 要找"能做到的办法"；有不可违反的条件；选项离散 | `candidate_tree` |
| 冷启动与自举 | `cold-start.md` | 通用 | 要 A 才能得到 B，要 B 才能得到 A | `dependency_graph` |
| 规划与调度 | `planning.md` | 通用 | 要安排一串动作；有先后、时间、资源限制 | `dependency_graph` |
| 优化与对偶 | `optimization.md` | 通用 | 要"最好的"，有取舍；目标能量化 | `candidate_tree` |
| 瓶颈与最小割 | `bottleneck.md` | 通用 | 产出被某个环节卡住；问"卡在哪""谁受益" | `generic_graph` |
| 推断与逆问题 | `inference.md` | 通用 | 看得到结果，要反推原因或参数 | `generic_graph` |
| 诊断与故障定位 | `diagnosis.md` | 通用 | 有症状，要找出哪里坏了 | `candidate_tree` |
| 不确定下的决策 | `decision-under-uncertainty.md` | 通用 | 要现在选，结果取决于不确定的未来 | `decision_tree` |
| 博弈与激励 | `game-and-incentives.md` | 通用 | 结果取决于其他人或机构怎么反应 | `generic_graph` |
| 反馈与动力系统 | `feedback-dynamics.md` | 通用 | 变量互相影响、随时间演化 | `generic_graph` |
| 搜索与筛选 | `search-and-screen.md` | 通用 | 在大量现成选项里找符合条件的那个 | `candidate_tree` |
| 论证与证明 | `argument-and-proof.md` | 通用 | 要确认一个说法对不对，或要对外宣称结论 | `argument_graph` |
| 会计恒等式与守恒 | `accounting-identity.md` | 投资 | 有恒等关系约束的量：资产负债表、现金流、部门收支 | `argument_graph` |
| 因果识别 | `causal-identification.md` | 投资 | 要估计 X 对 Y 的因果效应，而不是相关 | `generic_graph` |
| 体制切换 | `regime-switching.md` | 投资 | 同一关系在不同时期参数不同或方向相反 | `decision_tree` |
| 从价格反解预期 | `price-implied.md` | 投资 | 想知道市场已经计入了什么 | `argument_graph` |

找不到匹配时：用最接近的继续，结案时写进 `retro.unmatched`；同类问题攒到 2 个案例，就补一个新母题文件（格式照抄任一现有文件）。
