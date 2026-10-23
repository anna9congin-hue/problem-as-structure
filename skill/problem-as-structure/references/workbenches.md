# 工作数据结构

工作结构由母题决定。每种结构是一个定义文件 `assets/workbenches/<type>.json`，声明节点类型、状态、边类型、不变量和渲染方式；`pas` 用同一个图引擎处理所有类型。`pas schema` 列出当前可用的类型。

## 起始集合

| 类型 | 用于 | 节点 | 边 / 结构 | 关键规则 |
|---|---|---|---|---|
| `candidate_tree` 候选树 | 约束满足、搜索与筛选 | goal、category、candidate、subgoal、relax | 用 `parent` 成树 | 软偏好只能搁置；未核实不得淘汰；同层失败两次提冲突核；全部出局时重审搁置项；软偏好参照检验 |
| `dependency_graph` 依赖图 | 冷启动与自举、规划与调度 | item、relay（中继，写 produces）、action | requires、produces；环写在 `extra.cycles` | 环必须标出；中继不能依赖环里的任何节点 |
| `decision_tree` 决策树 | 不确定下的决策 | choice、scenario（p 或 p_unknown）、outcome、probe | 用 `parent` 成树；probe —informs→ scenario | 情景要么有概率要么标未知，已知概率之和不超过 1；选择标是否可逆 |
| `argument_graph` 论证图 | 论证与证明、投资论点、论文主张 | claim（statement、coverage、prediction、update_log） | depends_on（edge：conclusion、method、cites） | 等级由验证计算；撤回沿结论与方法边连带；预测到期必须结算 |
| `generic_graph` 通用图 | 没有合适结构时 | node | rel | 标 `standardize_pending`，结案时写进 `retro.unmatched` |

一个案例最多一棵主候选树、一张主论证图，其余类型可以有多个。不同结构之间的对应关系写在顶层 `links`。

## 节点的公共字段

`id`、`kind`、`status`、`label`（论证图用 `statement`）、`parent`（树形结构）、`round`、`proposed_by`、`note`、`evidence`、`pruned_by`、`parked_by`、`park_reference`、`attrs`、`conditions`（出局或搁置在什么前提下成立）、`decided_at`（之后才知道的证据不能支持这个决定）、`history`。

## 扩展：增加一种新结构

1. 同一种临时结构（`generic_graph` 加同样的用法）在 2 个以上案例出现，就值得标准化。
2. 写定义文件，格式见 `assets/workbench.meta.schema.json`：
   - `node_types`：每种节点的字段（JSON Schema）；
   - `statuses`：状态及其显示，`live`、`out` 表示是否算活的或出局；
   - `transitions`：允许的状态转移，或 `"any"`；
   - `edge_types`：边类型和端点限制；
   - `invariants`：声明式规则（`tree`、`acyclic`、`cycles_marked`、`not_reaches`、`status_requires`、`ref_exists`、`ref_filter`、`evidence_verified`、`children_prob`、`field_present`），表达不了的写 `hook`，实现放在 `scripts/pas_lib/checks/<模块>.py`；rule 和 remind 级必须写 `action`；
   - `render`：树、图还是表。
3. 加至少一个坏数据测试和一个干净样本，跑测试。
4. 在用到它的母题文件里把 `workbench` 指向它。
5. 定义升级时提高 `version`；旧案例用 `pas migrate` 迁移。
