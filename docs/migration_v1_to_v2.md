# v1 → v2 迁移规则（M0 定稿，M1 实现 `pas migrate`）

迁移必须**无损**：v1 的每个字段在 v2 里都有位置；迁移后再渲染，候选树和论断部分与 v1 输出逐字一致（差分测试）。

| v1 | v2 | 说明 |
|---|---|---|
| `schema_version: 1` | `schema_version: 2` | — |
| 顶层其余字段 | 原样保留 | `source`、`agent`、`domain`、`stages`、`pending`、`running`、`solution`、`retro` 字段名不变 |
| `archetypes[].status = active` | `accepted` | `candidate`、`rejected` 不变；v2 新字段（surface_cues 等）不补，迁移后由 AR-02 提醒 |
| `archetypes[]` 没有 `workbench` | 第一个 accepted 的母题指向 `candidate_tree` | 只在案例有节点时；不猜测其他母题的结构 |
| `nodes[]` | `workbenches[0]`：`{id: "W1", type: "candidate_tree", type_version: 1, archetypes: [所有 accepted 母题], nodes: v1 nodes}` | 节点 ID、字段原样保留 |
| `claims[]` | 一个 `argument_graph` 工作结构：`{id: "W2"（或下一个编号）, type: "argument_graph", type_version: 1, nodes: [每条论断加 kind: "claim"、status 缺省为 current]}` | 论断 ID、字段原样保留 |
| `links[]` 中两端都是论断的 `depends_on` | 移到该 argument_graph 的 `edges`（保留 `edge`、`note`） | — |
| `links[]` 其余 | 原样保留在顶层 `links` | — |
| `verifications[]` | 原样保留 | v1 的失败记录没有 `cause`，迁移时不补。迁移在顶层写 `migration: {from: 1, date}`；日期不晚于迁移日的失败记录缺 cause 时，VF-01 只提醒；之后新写入的失败一律按 error 处理 |
| `evidence[]` | 原样保留；`observed_at` 不补，缺省取 `date` | — |
| 其余 | 原样保留 | — |

迁移后自动核对：
1. `pas check` 只允许出现 v1 也报过的错误或提醒，以及 v2 新增规则的提醒（AR-02、AR-05、CT-12、VF-03），逐条列出。
2. `pas render` 的候选树、论断两部分，与 `tests/fixtures/<case>/v1/tree.md` 对应段落逐字一致。
