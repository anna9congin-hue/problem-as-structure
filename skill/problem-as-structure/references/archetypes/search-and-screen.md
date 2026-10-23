# 搜索与筛选（`search-and-screen`）

> 领域：通用。工作结构：`candidate_tree`。

```yaml
id: search-and-screen
name: 搜索与筛选
workbench: candidate_tree
recognize:
  surface_cues: ["推荐一个", "哪个好"]
  structural_checks: ["选项能被列举", "条件能逐条检查"]
  discriminating_test: "选项能列全吗？不能 → 先列全这一类的玩家，不只最出名的"
```

**识别特征**：在大量现成选项里找符合条件的那个。

**方法步骤**：

1. 先把这一类的玩家列全
2. 硬条件逐条过滤
3. 剩下的按软条件排序（软条件写参照对象）

**合适表示**：候选树：类别 → 玩家。

**在原问题里怎么验证**：查原文条款、实际试用。

**适用假设**：选项能列举。

**失效信号**：过滤后为空 → 约束满足：查冲突核、放松约束。

**常见陷阱**：只列最出名的几个。

**例子**：在信用构建账户这一类里比较 Kikoff、Self、Chime；找房；选工具。
