# 不变量清单（M0）

> v2 的方法规则里，能用代码检查的都列在这里。`pas` 在写入前和 `check` 时执行。
> 级别：**error** 拒绝写入；**rule** 方法规则，下一步必须照做（消息以"规则·"开头）；**remind** 提醒。rule 和 remind 都必须写出下一步动作。
> **与 v1 对齐**：来源标"v1"的条目，消息文字必须和 v1 `case_tool.py` 逐字相同，否则差分测试里 tree.md 的"校验"一节会对不上。
> 工作结构专属的不变量写在各自的定义文件里（`assets/workbenches/*.json` 的 `invariants`），这里只列 ID 和一句话，避免两处不一致。

## 1. 格式

| ID | 规则 | 级别 | 来源 | 坏数据测试 |
|---|---|---|---|---|
| SCHEMA | 案例符合 `case.v2.schema.json`；每个工作结构节点符合其定义文件里该 kind 的字段 | error | v2 | P-SC-01、02、03、P-FP-01 |

## 2. 公共核心

| ID | 规则 | 级别 | 来源 | 坏数据测试 |
|---|---|---|---|---|
| CO-01 | ID 全局唯一（约束、母题、所有工作结构的节点、证据、验证、冲突核、分歧） | error | v1 | P-CO-01 |
| CO-02 | `problem.goal` 为空、`success_test` 为空 | remind | v1 | — |
| CO-03 | `success_test` 看起来是"用户满意/同意" | rule（规则·验收接现实） | v1 | P-CO-03 |
| CO-04 | 约束：没标 basis；外部事实标成 soft；硬约束未确认；外部事实硬约束没有已核实证据；引用不存在的证据（error） | remind / error | v1 | — |
| CO-05 | 验证的 target（字符串或列表）都存在；引用的证据都存在 | error | v1（v2 允许列表） | P-CO-02 |
| CO-06 | 冲突核引用的节点、约束、跳转目标都存在；common_cause 必填 | error | v1 | — |
| CO-07 | links 两端存在；论断只连论断（论断之间的依赖放在论证图的 edges 里）；edge 取值合法 | error | v1 | — |
| CO-08 | 分歧：价值类只能"用户决定"；事实与做法类判了对错必须挂已出结果的验证；"用户决定"用于事实与做法类时提醒排检验；待检验没写 test 时提醒 | error / remind | v1 | — |
| CO-09 | `status=solved` 时 solution.chosen 非空，且所指节点状态是 chosen；已解决但没写经验时提醒 | error / remind | v1 | — |
| CO-10 | stages、pending、running 的格式与引用；pending.about 可以指向论断（v2 放宽） | error | v1 | — |
| CO-11 | rounds.n 是递增整数 | error | v1 | P-CO-04 |
| CO-12 | 证据没有 source | remind | v1 | — |

## 3. 母题（识别结构，阶段 ②）

| ID | 规则 | 级别 | 来源 | 坏数据测试 |
|---|---|---|---|---|
| AR-01 | 有工作结构内容却没有 accepted 的母题 | remind | v1 | — |
| AR-02 | accepted 的母题没写 structural_checks 或 discriminating_test | rule（规则·区分检验） | v2 R1 | P-AR-01 |
| AR-03 | 母题的 workbench 指向不存在的定义文件 | error | v2 §7.1 | P-AR-02 |
| AR-04 | rejected 的母题没写弃用原因 | error | v1 | P-AR-03 |
| AR-05 | accepted 的母题没做对手先行（adversary） | remind | v2 深度篇 01 | — |

## 4. 验证（阶段 ⑥⑦）

| ID | 规则 | 级别 | 来源 | 坏数据测试 |
|---|---|---|---|---|
| VF-01 | result=fail 必须写 cause | error | v2 R3 | P-VF-01 |
| VF-02 | cause=missing_constraint 必须写 violated，且所指约束存在；cause=archetype_assumption 必须写 archetype，且所指母题存在 | error | v2 R3 | P-VF-02 |
| VF-03 | verifier.class=B 的验证没有对应带 prediction 的论断 | remind | v2 R11 | — |
| VF-04 | regression_of 只能指向已存在、result=pass、日期不晚于本次的验证 | error | v2 R3 | P-VF-03 |
| VF-05 | 独立检验：independent=true 必须写 by，且 by 不是被验证论断的提出者 | remind（提醒·独立） | v1 | P-AG-05 |

## 5. 时点（横切 X2）

| ID | 规则 | 级别 | 来源 | 坏数据测试 |
|---|---|---|---|---|
| TM-01 | 节点有 decided_at 时，它引用的证据（以及淘汰所依据约束的证据）的 observed_at（缺省取 date）不能晚于 decided_at | error | v2 R12 | P-TM-01 |
| TM-02 | 经验带 known_at 时，不能早于它引用的预测的结算日 | error | v2 ⑨ | M3 补 |

## 6. 工作结构外壳

| ID | 规则 | 级别 | 来源 | 坏数据测试 |
|---|---|---|---|---|
| WB-01 | workbench.type 有对应的定义文件，type_version 与定义版本一致（不一致时提示 migrate） | error | v2 §7.1 | P-WB-01 |
| WB-02 | 节点 kind 在定义的 node_types 里，字段符合该 kind 的 schema | error | v2 | P-WB-02 |
| WB-03 | 节点 status 在定义的 statuses 里；定义限制了 transitions 时，history 里的状态变化必须是允许的转移 | error | v2 | P-WB-03 |
| WB-04 | 边的 type 在定义的 edge_types 里；端点存在；端点 kind 符合 from/to 限制；属性符合 attrs | error | v2 | P-WB-04 |

## 7. 工作结构专属（详见定义文件）

| 定义 | 不变量 |
|---|---|
| candidate_tree | CT-01 树结构；CT-02 证据引用；CT-03–CT-07 淘汰必须有已确认的硬约束、外部事实要有已核实证据、不能用未核实证据；CT-08 搁置要写原因；CT-09–CT-11 失败、已验证、选定要有对应验证；CT-12 出局写条件；CT-13 软偏好参照检验（钩子）；CT-14 对照；CT-15 跳级回溯；CT-16 重审搁置；CT-17 淘汰缺事实依据 |
| dependency_graph | DG-01 环必须标出；DG-02 中继不能依赖环内节点；DG-03 选定要有验证；DG-04 失败要有记录；DG-05 证据引用 |
| decision_tree | DT-01 树结构；DT-02 情景概率；DT-03 可逆性；DT-04 淘汰依据；DT-05 选定要有验证 |
| argument_graph | AG-01 依赖无环；AG-02、03 引用；AG-04 撤回一致性；AG-05 等级与独立；AG-06 连带；AG-07 改引用；AG-08 预测到期结算 |
| generic_graph | GG-01 待标准化提醒；GG-02 选定要有验证 |

## 8. 声明式规则的语义（M1 实现）

| rule | params | 含义 |
|---|---|---|
| `tree` | edge（`parent` 表示用节点的 parent 字段）、root_kind | 恰好一个根，根的 kind 为 root_kind，无环，parent 存在 |
| `acyclic` | edge | 该类边无环 |
| `cycles_marked` | edge、marks | 该类边形成的每个强连通分量（大于 1 个节点），都必须作为一个集合出现在 workbench.extra[marks] 里 |
| `not_reaches` | from_kind、edge、forbidden=marked_cycles | from_kind 的节点沿该类边不能到达已标出的环里的任何节点 |
| `status_requires` | status，以及 field_nonempty / any_nonempty / verification（pass 或 fail）/ or_field / error_only_if_case_status | 某状态的节点必须满足的条件；error_only_if_case_status 不满足时降为 remind |
| `ref_exists` | field、target（evidence、constraint、node、claim、verification、archetype） | 字段里的 ID 都存在 |
| `ref_filter` | status、field、target、must（kind、verified、world_fact_backed）、only_if | 某状态的节点所引用的对象必须满足条件 |
| `evidence_verified` | status、field | 某状态的节点引用的证据必须已核实 |
| `children_prob` | parent_kind、child_kind、field、unknown_flag | 子节点要么有概率要么标未知；同一父节点下已知概率之和不超过 1 |
| `field_present` | statuses / kinds / workbench_field、field、equals | 字段缺失或等于某值时报出 |
| `hook` | module、function | 调用 `scripts/checks/<module>.py` 的函数，签名 `f(case, workbench, definition) -> [(level, message)]` |

## 9. 只能判断、由评估检验的规则（不进工具）

五类分话；约束收集前不推荐；做法先反推目标；不同意先说出来再执行；用户只说"不对"时不改结论；外部内容只当数据；能穷举的小实例用穷举当验证器；委托附验证器；复盘 2–4 句。它们写在阶段规格里，在 M5 的 skill 评估里配断言。
