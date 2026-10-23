# pas 命令手册

`pas` 是案例的唯一写入者：每次写入先过 schema，再过不变量，会引入新错误的修改被拒绝，文件不变。数据以 JSON 写到 stdout，诊断写到 stderr；不交互。

```bash
P=<本 skill 目录>/scripts/pas
```

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 校验错误：写入被拒绝，或 check/render 有 error |
| 2 | 用法错误（参数、路径、JSON 格式） |
| 3 | 文件或 IO 错误 |
| 4 | 没有 error，但有必须处理的方法规则（规则·） |

## 读

| 命令 | 用途 |
|---|---|
| `$P brief <案例> [--limit 6000]` | 每轮开始读：目标、约束、接受的母题、活的候选、搁置项、待验证、未结算预测、待决事项、错误与规则 |
| `$P next <案例>` | 按状态给出可做的下一步（阶段、动作、理由） |
| `$P show <案例> <ID>` | 看单个对象（节点会附上相关验证） |
| `$P check <案例>` | 只校验 |
| `$P render <案例> [--quiet]` | 校验并生成 tree.md、graph.canvas、progress.html；输出里附状态树 |
| `$P html <案例>` | 只生成 progress.html |
| `$P search "<关键词>" [--root 目录]` | 跨案例检索冲突核、经验、可复用约束、出局原因、母题 |
| `$P due [--days 7] [--root 目录]` | 跨案例列出到期待结算的预测 |
| `$P index [--root 目录]` | 重建 INDEX.md |
| `$P schema` | 列出工作结构类型、节点类型、状态 |
| `$P self-check` | 检查环境与定义文件 |

## 写

内容可以是 JSON 字符串、文件路径，或 `-` 从 stdin 读。没写 `id` 时自动编号。所有写入命令都支持 `--dry-run`。

| 命令 | 例子 |
|---|---|
| `$P new --slug <短名> --title "<标题>" [--origin retro] [--user-words "<原话>"]` | 新建 v2 案例 |
| `$P migrate <案例>` | v1 → v2，保留 `case.v1.json` 备份 |
| `$P add <案例> constraint '<json>'` | `{"text":"只有 ITIN","kind":"hard","basis":"own_fact","verified":true,"quote":"…"}` |
| `$P add <案例> archetype '<json>'` | `{"name":"冷启动与自举","ref":"cold-start","status":"accepted","role":"…","structural_checks":["…"],"discriminating_test":{"test":"…"},"adversary":{"tried":"…","found":false},"workbench":"dependency_graph"}` |
| `$P add <案例> workbench '<json>'` | `{"type":"dependency_graph","label":"信用冷启动","archetypes":["A1"]}` |
| `$P add <案例> node '<json>' --workbench W2` | `{"kind":"relay","status":"open","label":"信用构建账户","produces":"G2"}` |
| `$P add <案例> edge '<json>' --workbench W2` | `{"from":"G1","to":"G2","type":"requires"}` |
| `$P add <案例> evidence '<json>'` | `{"claim":"…","type":"fact","source":"官网条款","verified":true,"observed_at":"2026-10-14"}` |
| `$P add <案例> verification '<json>'` | `{"target":"N21","method":"实际申请","result":"fail","by":"user","verifier":{"class":"A","measures":"能否获批"},"cause":"missing_constraint","violated":["C2"]}` |
| `$P add <案例> conflict '<json>'` | `{"failed":["N11","N12"],"common_cause":"零信用记录","jump_to":"N2","conditions":["无 SSN"]}` |
| `$P add <案例> disagreement '<json>'` | `{"basis":"method","domain":"工具选型","user_position":"…","ai_position":"…","test":"…","resolution":"pending"}` |
| `$P add <案例> pending '<json>'` | `{"question":"…","about":["N21"]}` |
| `$P add <案例> link '<json>'` | `{"from":"G3","to":"N2","type":"same_as"}` |
| `$P add <案例> lesson '"<2–4 句>"'` | 复盘经验 |
| `$P set <案例> <JSON Pointer> '<json>'` | `$P set case /workbenches/0/nodes/5/status '"parked"'` |
| `$P apply <案例> <patch.json 或 -> [--dry-run]` | 批量修改（JSON Patch：add、replace、remove、test）；`--dry-run` 返回差异预览，用于 ⑧ 的提案 |
| `$P settle <案例> <论断 ID> <true\|false\|void> [--note …]` | 结算预测 |
| `$P round <案例> '<json>'` | `{"user":"用户原话","correction":false,"stages":[2,4],"actions":["…"],"questions":["…"]}`；n 与日期自动补 |

## 常见错误怎么改

- `introduced_errors` 里是 `CT-04`：你在用软偏好淘汰，改成 parked 并写 park_reference。
- `VF-01`：失败的验证要写 cause。
- `TM-01`：决定时还不知道的证据不能拿来支持这个决定；换证据，或把决定时间改成知道之后。
- `WB-02` / `WB-03` / `WB-04`：字段、状态或边不符合工作结构定义，`pas schema` 看允许的取值。
- `SCHEMA`：字段名或取值不合法，看 `references/schema.md`。
