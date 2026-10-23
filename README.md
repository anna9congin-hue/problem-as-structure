# problem-as-structure v2

一个 Agent Skill：遇到多约束、反复碰壁的复杂现实问题时，先识别问题的数学本质结构（近似母题），调用这个母题的经典方法，建方法要求的工作数据结构，人和 AI 沿方法推进，最后带回原问题验证，并经用户的价值确认。自然语言只用于输入和输出。

配套论文：《问题即结构，语言即外壳》。

## 流水线

```
① 拆解输入 → ② 识别结构 → ③ 经典方法 → ④ 工作数据结构 → ⑤ 人机协作
      ↑                                                        ↓
⑨ 沉淀 ← ⑧ 价值门 ← ⑦ 诊断（失败按原因回 ①/②/⑤） ← ⑥ 原问题验证
```

三个横切机制：X1 人机分工，X2 验证纪律，X3 上下文与委托。每个阶段的目的、操作、关卡见 `skill/problem-as-structure/references/stages.md`。

## 目录

```
skill/problem-as-structure/      # 要安装的 skill（复制这个目录即可）
  SKILL.md
  assets/case.v2.schema.json     # 案例公共核心
  assets/workbench.meta.schema.json
  assets/workbenches/*.json      # 工作结构定义：candidate_tree、dependency_graph、decision_tree、argument_graph、generic_graph
  references/                    # 阶段规格、工作结构、pas 手册、schema、16 个母题、投资领域包
  scripts/pas                    # 唯一写入者（Python 3 标准库，在 3.12 上测试）
  scripts/case_tool.py           # v1 命令兼容层
tests/                           # 不需要模型的测试
  v1_reference/case_tool.py      # 冻结的 v1 工具（差分测试参照）
  fixtures/                      # 3 个真实案例快照和 v1 输出（MANIFEST.json 记 SHA-256）
  poison/                        # 37 个坏数据测试
  run_tests.py
tools/                           # m0_check、check_skill（--installs 查安装漂移）、replay_itin、freeze_v1
docs/invariants.md               # 不变量清单
docs/migration_v1_to_v2.md       # 迁移规则
evals/                           # 需要模型的评测（尚未运行）
```

## 安装

把 `skill/problem-as-structure/` 复制到 agent 的 skills 目录，例如：

```
rsync -a --delete --exclude=__pycache__ skill/problem-as-structure/ ~/.kiro/skills/problem-as-structure/
```

v1 的案例用 `scripts/pas migrate <案例目录>` 升级，会留下 `case.v1.json` 备份。

## 测试

```
python3 tools/m0_check.py        # schema、定义文件、夹具
python3 tests/run_tests.py       # 差分（v1 输出逐字一致）、坏数据、命令、随机写入序列
python3 tools/check_skill.py     # skill 结构，v1 规则全部有落点
python3 tools/replay_itin.py     # ITIN 案例用 v2 重走
```

公开仓库不含 `tests/fixtures/`（作者的真实案例），差分测试和 ITIN 回放会自动跳过；坏数据测试、命令测试、随机写入序列照常运行。

## 里程碑

| 里程碑 | 状态 |
|---|---|
| M0 schema、定义文件、不变量、夹具 | 完成 |
| M1 读、校验、渲染、migrate | 完成（差分测试逐字一致） |
| M2 写入命令、apply、brief、next、due、search、settle | 完成 |
| M3 母题算子（16 个）、投资领域包、阶段规格、SKILL.md | 完成 |
| M4 ITIN 与论文案例回放 | 完成 |
| M5 同步、发布、评测集 | 同步与发布完成；模型评测已写好，未运行 |

## 许可

MIT，见 `LICENSE`。
