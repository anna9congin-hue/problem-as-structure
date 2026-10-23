# Evals（未运行）

这些评测要调用模型，有费用，**目前一次都没跑过**。`tests/` 下的测试不需要模型，已全部通过；这里的评测检查的是"模型用这个 skill 时行为对不对"。

## 内容

- `triggers.json`：40 条查询，20 条应触发、20 条不应触发；`split=train`（24 条）用于调 SKILL.md 的 description，`split=test`（16 条）留作检验，不参与调整。
- `tasks/itin.json`：ITIN 信用卡对话，4 轮，11 条断言，对应 ①–⑨ 的关卡。
- `tasks/paper.json`：续接论文案例，3 轮，7 条断言，测续接和 ⑤–⑦ 的纪律。

## 怎么跑

1. 触发：对每条查询，在装了本 skill 的 agent 里新开会话，记录是否加载了 `problem-as-structure`。统计 train/test 上的准确率；只用 train 的错误改 description，改完再看 test。
2. 任务：每个任务跑两组，各 3 次：装 skill 与不装 skill。每轮后用 `pas check <dir>` 和断言里的 `auto` 列判分；标 `manual` 的由人判。
3. 报告写进论文目录 `reports/`，包含每条断言的通过次数和两组差异。

## 判分约定

- `pas check` 退出码：0 通过；4 有必须处理的方法规则（不算失败，但记录）；1 有错误（算失败）。
- 断言 A11 / B6 是硬条件：出现退出码 1 即该次运行失败。
