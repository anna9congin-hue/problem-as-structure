# case.json v2 字段说明

完整定义：`assets/case.v2.schema.json`（公共核心）与 `assets/workbenches/*.json`（各工作结构）。这里只列含义；取值以 schema 为准。

## 顶层

`schema_version`（2）、`id`（目录名）、`title`、`status`（open、converging、solved、parked、abandoned）、`origin`（live、retro）、`source`、`created`、`updated`、`agent`、`domain`、`migration`（由 migrate 写入）、`problem`、`constraints`、`archetypes`、`workbenches`、`links`、`evidence`、`verifications`、`conflicts`、`disagreements`、`rounds`、`stages`、`pending`、`running`、`solution`、`retro`。

## problem

`user_words`（原话，不改字）、`goal`、`query_type`（feasible、optimal、posterior、cause、policy、proof）、`initial_state`、`success_test`（必须能在原问题里观察到）、`fast_path`（`{reason}`，走快速通道时填）。

## constraints[]

`id`（C1…）、`text`、`kind`（hard、soft）、`basis`（value 用户的价值；own_fact 用户自身处境；world_fact 外部世界，由证据决定）、`evidence`、`source`、`quote`、`verified`（用户是否确认；world_fact 还要有已核实证据）。

## archetypes[]

`id`（A1…）、`name`、`ref`（母题文件 id）、`status`（candidate、accepted、rejected）、`role`（负责问题的哪一部分）、`mapping`、`representation`、`method`、`assumptions`、`failure_signals`、`surface_cues`（表面线索）、`structural_checks`（真正成立的条件）、`discriminating_test`（`{test, result, versus}`）、`adversary`（`{tried, counterexample, found}`）、`workbench`（工作结构类型）、`note`（拒绝原因）。

## workbenches[]

`id`（W1…）、`type`、`type_version`、`label`、`archetypes`、`nodes`、`edges`、`extra`（定义文件声明的结构级字段，例如依赖图的 `cycles`）、`standardize_pending`。节点公共字段见 `workbenches.md`。

## evidence[]

`id`（E1…）、`claim`、`type`（fact、computation、test、prediction、preference）、`source`、`verified`、`date`、`observed_at`（什么时候知道的，缺省取 date）、`untrusted_source`（来自外部文档）。

## verifications[]

`id`（V1…）、`target`（一个或多个对象 ID）、`method`、`result`（pass、fail、pending）、`date`、`evidence`、`by`（检验者：ai、user 或外部 agent 名）、`independent`、`rerun`（能复现判定本身的命令）、`verifier`（`{class: A|B|C, measures, fp_risk: low|medium|high}`）、`cause`（失败时必填：missing_constraint、archetype_assumption、implementation）、`violated`、`archetype`、`regression_of`、`note`。

## conflicts[]

`id`（K1…）、`failed`、`common_cause`、`constraint`、`jump_to`、`conditions`、`round`、`note`。

## disagreements[]

`id`（D1…）、`round`、`about`、`basis`（value、own_fact、world_fact、method）、`domain`（问题类型，用于统计可信度）、`user_position`、`ai_position`、`reason`、`test`、`resolution`（pending、user_right、ai_right、both_partly、user_decides）、`verification`、`note`。价值类只能 user_decides；事实与做法类判对错要挂已出结果的验证。

## rounds[]

`n`（递增）、`date`、`user`、`correction`、`stages`（涉及的阶段 1–9）、`actions`、`questions`、`real_world_attempt`（`{target, result, note}` 或 null）。

## stages[]、pending[]、running[]

进展面板用：阶段图（`id、label、status、outputs、missing、depends_on、nodes`）；等用户决定的事（`id、question、about、since_round`）；后台任务（`label、report_path、started`）。

## solution、retro

`solution`：`chosen`、`alternatives`、`summary`。`retro`：`lessons`（字符串，或 `{text, round, known_at}`）、`reusable_constraints`、`archetype_fit`、`unmatched`（找不到匹配母题的部分）。

## 论断（argument_graph 的 claim 节点）

`statement`（冻结；改陈述就新开一条，用 `supersedes` 指向旧的）、`proposed_by`、`about`、`evidence`、`coverage`（`{checked, not_covered, weaker_than_claim}`）、`withdrawal`（`{date, root_cause, scope: proof|statement}`）、`prediction`（`{statement, falsifier, settle_by, p, made_at, event: {date, label, if_good, if_bad}, outcome: {date, result: true|false|void, note}}`）、`update_log`（`[{round, evidence, effect: strengthen|weaken|neutral, action}]`）、`history`。状态：current、superseded、withdrawn、refuted。

等级（自动计算）：V0 没有通过的验证；V1 有通过的验证；V2 通过且带 `rerun`；V3 通过且 `independent: true`、写明 `by`、`by` 不是提出者。`coverage.weaker_than_claim` 为真时降一级。
