# case.json 字段说明

`case.json` 是案例的唯一真源。`tree.md`、`graph.canvas`、`INDEX.md` 都由 `case_tool.py` 生成，不要手改。ID 在整个案例里全局唯一。

## 顶层

| 字段 | 含义 | 取值 |
|---|---|---|
| `schema_version` | 格式版本 | `1` |
| `id` | 案例 ID，等于目录名 | `2026-10-14_itin-credit-builder` |
| `title` | 标题 | |
| `status` | 案例状态 | `open` 进行中、`converging` 收敛中、`solved` 已解决、`parked` 暂停、`abandoned` 放弃 |
| `origin` | 来源 | `live` 实时求解、`retro` 从旧对话回填 |
| `source` | 原始材料 | `{path, note}` |
| `created` / `updated` | 日期 | ISO 日期 |
| `agent` | 哪个 AI 维护的 | |
| `domain` | 领域标签 | 列表，如 `["个人金融"]` |

## `problem`

| 字段 | 含义 |
|---|---|
| `user_words` | 用户提出问题时的原话，不改字 |
| `goal` | 目标，一句话 |
| `query_type` | `feasible` 求可行解、`optimal` 求最优解、`posterior` 求估计、`cause` 求原因、`policy` 求策略、`proof` 求证明 |
| `initial_state` | 初始状态，列表 |
| `success_test` | 怎样算解决了，必须能在原问题里检验 |

## `constraints[]`

| 字段 | 含义 |
|---|---|
| `id` | `C1`、`C2`… |
| `text` | 约束内容 |
| `kind` | `hard`（违反即不可接受）或 `soft`（偏好） |
| `basis` | 谁说了算：`value` 用户的价值或偏好（用户决定）；`own_fact` 用户自身处境（用户是最可靠的证人）；`world_fact` 对外部世界的判断（由证据决定，用户说了不算） |
| `evidence` | 支撑这条约束的证据 ID。`world_fact` 类硬约束要有一条已核实的证据，才能用来淘汰 |
| `source` | 出处：用户原话所在轮次、文档、推断 |
| `quote` | 用户原话 |
| `verified` | 用户是否确认过。未确认的硬约束不能用来淘汰；对 `world_fact` 来说，用户确认不够，还要有证据 |

## `archetypes[]`（近似母题）

| 字段 | 含义 |
|---|---|
| `id` | `A1`… |
| `name` | 母题名，取自 `archetypes.md` |
| `status` | `candidate` 候选、`active` 在用、`rejected` 弃用（`note` 写原因） |
| `mapping` | 原问题的什么对应母题的什么 |
| `representation` | 用什么表示（分组方式、图的形状） |
| `method` | 基本解法 |
| `assumptions` | 映射成立的前提，列表 |
| `failure_signals` | 出现哪些情况说明这个母题不适用，列表 |
| `note` | 备注 |

## `nodes[]`（解空间）

| 字段 | 含义 |
|---|---|
| `id` | `N0` 为根，其余自定，建议按层编号（`N2`、`N23`、`N231`） |
| `label` | 节点内容 |
| `parent` | 父节点 ID；根节点为 `null` |
| `kind` | `goal` 目标、`category` 类别、`candidate` 具体候选、`subgoal` 子目标（多由冲突核跳转产生）、`relax` 放松某条约束的方案 |
| `status` | `open` 待评估、`expanded` 已展开、`pruned` 淘汰、`parked` 搁置、`failed` 失败、`verified` 已验证、`chosen` 选定 |
| `round` | 首次出现的轮次 |
| `proposed_by` | 谁提出的：`user` 或 `ai`。用户提出的做法是候选，不是约束；被选定前同层要有经过评估的对照 |
| `pruned_by` | 淘汰时违反的硬约束 ID，必须是已确认的硬约束 |
| `parked_by` | 搁置时涉及的约束 ID（通常是软偏好） |
| `park_reference` | 因软偏好搁置时的比较：`{measure, direction, compared_to, external, note}`。`measure` 比较维度（如 `cost_month`）；`direction` 为 `lower`（越低越好，默认）或 `higher`；`compared_to` 台账里的参照节点；`external` 台账外的参照（如"免费信用卡"）。参照节点全部出局、或本节点已是可行集合里该维度最好的，脚本会提醒重审。回填时，节点被重新启用后仍保留该字段作为记录 |
| `attrs` | 可比较的数值属性，如 `{"cost_month": 5, "wait_days": 30}`。键名与 `park_reference.measure` 一致，脚本才能在可行集合里比较 |
| `evidence` | 支撑判断的证据 ID；用于淘汰时必须已核实 |
| `note` | 备注；搁置或失败没有对应记录时，原因写这里 |
| `history` | 状态变化记录：`[{round, status, note}]` |

## `links[]`

节点之间树结构以外的关系：`{from, to, type, note}`，`type` 如 `reframed_to`（换了问法）、`depends_on`、`same_as`。

## `conflicts[]`（冲突核）

| 字段 | 含义 |
|---|---|
| `id` | `K1`… |
| `failed` | 一起失败或受阻的节点（可以包含因同一原因被搁置的节点） |
| `common_cause` | 共同原因 |
| `constraint` | 对应的约束或初始状态条目（可空） |
| `jump_to` | 跳到的上一层节点（新的子目标） |
| `round` | 提取出来的轮次 |
| `note` | 备注 |

## `disagreements[]`（人机分歧）

用户与 AI 意见不同时记一条。这组数据回答"谁在什么问题上是天花板"。

| 字段 | 含义 |
|---|---|
| `id` | `D1`… |
| `round` | 轮次 |
| `about` | 涉及的节点或约束 ID |
| `basis` | 分歧的类别：`value`、`own_fact`、`world_fact`、`method`（做法） |
| `user_position` | 用户的立场 |
| `ai_position` | AI 的立场与理由 |
| `test` | 用什么检验来分出对错 |
| `resolution` | `pending` 待检验、`user_right` 用户对、`ai_right` AI 对、`both_partly` 各对一部分、`user_decides` 用户决定 |
| `verification` | 判定对错所依据的验证 ID |
| `note` | 备注 |

规则：`value` 类分歧没有对错，只能 `user_decides`；`world_fact` 与 `method` 类判 `user_right`、`ai_right`、`both_partly` 时，必须挂一条已出结果的验证；`user_decides` 用在这两类上时，表示"按用户意见执行、但未验证"，脚本会提醒把检验排进下一步。

## `evidence[]`

| 字段 | 含义 |
|---|---|
| `id` | `E1`… |
| `claim` | 断言内容 |
| `type` | `fact` 事实、`computation` 计算、`test` 实测、`prediction` 预测、`preference` 用户偏好 |
| `source` | 出处（链接、文件行号、对话编号） |
| `verified` | 是否已核实（用户看到原文或实测） |
| `date` | 日期 |

## `verifications[]`（原问题里的验证）

| 字段 | 含义 |
|---|---|
| `id` | `V1`… |
| `target` | 被验证的节点 |
| `method` | 怎么验证的（实际申请、运行代码、查条款原文、用户确认…） |
| `result` | `pass`、`fail`、`pending` |
| `date` | 日期 |
| `evidence` | 相关证据 ID |
| `note` | 备注 |

## `rounds[]`（探索过程）

| 字段 | 含义 |
|---|---|
| `n` | 轮次，递增整数（回填时用对话编号） |
| `date` | 日期 |
| `user` | 用户本轮原话或要点 |
| `correction` | 用户本轮是否纠正了 AI |
| `actions` | 本轮对结构做了什么，列表 |
| `questions` | 本轮问了用户什么，列表 |
| `real_world_attempt` | 现实尝试：`{target, result, note}` 或 `null` |

## `solution` 与 `retro`

- `solution`：`chosen`（选定的节点）、`alternatives`（备选节点）、`summary`。
- `retro`：`lessons`（经验）、`reusable_constraints`（可复用的约束知识，如"押金卡都发实体卡"）、`archetype_fit`（母题是否合适、哪里不合适）。

## 脚本自动计算的指标

记录轮数、用户纠正次数、分歧数及各结果（用户对、AI 对、各对一部分、用户决定、待检验）、用户提出的节点数、现实尝试次数与失败次数、各状态节点数、冲突核数、母题更换次数、搁置后重新启用的节点数、解首次出现轮次、解选定轮次。后两项之差，就是"答案已经出现、却没被采用"的轮数。
