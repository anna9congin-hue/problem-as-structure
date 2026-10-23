#!/usr/bin/env python3
"""skill 目录的静态检查（发布前必跑）。

1. Agent Skills 规范：name 合法且与目录同名；description 1–1024 字符；SKILL.md 少于 500 行；
   SKILL.md 引用的 references/、assets/、scripts/ 文件都存在，且只引用一层。
2. v1 方法规则一条不丢：每条规则的关键说法都能在 SKILL.md 或 references/stages.md 里找到，
   或者在 docs/invariants.md 里有对应的不变量。
3. 母题文件格式：每个文件都有 recognize（surface_cues、structural_checks、discriminating_test）、
   方法步骤、工作结构、原问题里的验证；工作结构类型都有定义文件；索引列出了所有母题。
4. 三处安装与源头一致（--installs 时检查）。

用法：python3 tools/check_skill.py [--installs]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "problem-as-structure"
INSTALLS = [Path.home() / ".kiro/skills/problem-as-structure", Path.home() / ".codex/skills/problem-as-structure",
            Path.home() / ".gemini/config/skills/problem-as-structure"]

# v1 SKILL.md 的方法规则 → 必须出现的说法（任一即可）
V1_RULES = {
    "五类分话": ["五类分话"],
    "做法先反推目标、同层对照": ["先反推目标", "对照"],
    "不同意先说出来再执行": ["先说出来再执行"],
    "偏好权重归用户、比较由 AI 检验": ["偏好的权重归用户"],
    "约束的价格，不是方案的价格": ["约束的价格，不是方案的价格"],
    "成功检验不能是用户满意": ["不能是\"用户满意\"", "不用\"用户满意\""],
    "开案先看旧案例": ["pas search"],
    "一轮最多问 5 个，是/否与反例题": ["最多问 5 个", "最多 5 问"],
    "母题：映射、表示、解法、假设、失效信号": ["映射", "失效信号"],
    "表示决定难度：按前提分组": ["按\"每个候选要求什么前提\"分组", "按前提分组"],
    "先展开类别不重不漏": ["不重不漏"],
    "软偏好只能搁置": ["软偏好只能搁置"],
    "未核实的事实不得用于淘汰": ["未核实的依据只能搁置", "未核实不得淘汰", "未核实的事实没有用于淘汰"],
    "同层失败两次跳级回溯": ["同层失败两次"],
    "CEGAR 两种情况": ["漏了约束", "母题假设不成立"],
    "验证必须在原问题里做": ["母题内部推理成立不算验证"],
    "选定方案必须有通过的验证": ["选定方案有 pass 的验证"],
    "不说无解，全部出局时三步": ["不说\"无解\"", "重审每个搁置项"],
    "被搁置的候选不消失、主动重审": ["主动重审"],
    "用户说不对时定位、不默认任何一方错": ["既不默认自己错，也不默认用户错"],
    "不把用户的做法当约束": ["不把用户提出的做法当成约束"],
    "记录要诚实": ["记录要诚实"],
    "独立检验要写检验者": ["独立检验要写明检验者"],
    "委托附验证器": ["附上验证器"],
    "回复格式六项": ["回复格式"],
    "回填旧对话": ["回填旧对话"],
}


def main():
    fails = []
    F = fails.append
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        F("SKILL.md 没有 frontmatter")
        front = ""
    else:
        front = m.group(1)
    name = re.search(r"^name:\s*(.+)$", front, re.M)
    desc = re.search(r"^description:\s*(.+)$", front, re.M)
    if not name or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name.group(1).strip()) or len(name.group(1).strip()) > 64:
        F("name 不合法")
    elif name.group(1).strip() != SKILL.name:
        F("name 与目录名不一致")
    if not desc or not (1 <= len(desc.group(1).strip()) <= 1024):
        F(f"description 长度不合法：{len(desc.group(1).strip()) if desc else 0}")
    lines = text.count("\n")
    if lines >= 500:
        F(f"SKILL.md 有 {lines} 行，应少于 500")
    refs = set(re.findall(r"`((?:references|assets|scripts)/[^`\s]+)`", text))
    for r in refs:
        r = r.split(" ")[0]
        p = SKILL / r
        if "<" in r or "*" in r:
            continue
        if not p.exists():
            F(f"SKILL.md 引用的 {r} 不存在")
    body = text + (SKILL / "references" / "stages.md").read_text(encoding="utf-8")
    inv = (ROOT / "docs" / "invariants.md").read_text(encoding="utf-8")
    missing = [k for k, phrases in V1_RULES.items() if not any(p in body for p in phrases)]
    for k in missing:
        F(f"v1 规则没有落点：{k}")
    defs = {p.stem for p in (SKILL / "assets" / "workbenches").glob("*.json")}
    arch = sorted((SKILL / "references" / "archetypes").glob("*.md"))
    index = (SKILL / "references" / "archetypes" / "INDEX.md").read_text(encoding="utf-8")
    n_arch = 0
    for a in arch:
        if a.name == "INDEX.md":
            continue
        n_arch += 1
        t = a.read_text(encoding="utf-8")
        for need in ("surface_cues:", "structural_checks:", "discriminating_test:", "**方法步骤**", "**在原问题里怎么验证**", "workbench:"):
            if need not in t:
                F(f"母题 {a.name} 缺 {need}")
        wb = re.search(r"^workbench:\s*(\S+)", t, re.M)
        if wb and wb.group(1) not in defs:
            F(f"母题 {a.name} 的工作结构 {wb.group(1)} 没有定义文件")
        if f"`{a.name}`" not in index:
            F(f"母题索引没列出 {a.name}")
    installs = {}
    if "--installs" in sys.argv:
        for d in INSTALLS:
            r = subprocess.run(["diff", "-rq", "--exclude=__pycache__", str(SKILL), str(d)], capture_output=True, text=True)
            installs[str(d)] = "一致" if r.returncode == 0 else "不一致"
            if r.returncode:
                F(f"安装 {d} 与源头不一致")
    out = {"skill_md_lines": lines, "description_chars": len(desc.group(1).strip()) if desc else 0,
           "v1_rules_checked": len(V1_RULES), "archetypes": n_arch, "workbench_types": sorted(defs),
           "installs": installs, "failures": fails, "pass": not fails, "invariants_doc_lines": inv.count("\n")}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
