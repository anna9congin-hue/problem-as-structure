#!/usr/bin/env python3
"""problem-as-structure 案例工具：新建、校验、渲染、索引。只用 Python 标准库。

用法：
  case_tool.py new --slug itin-credit --title "用 ITIN 办美国信用卡" [--origin retro] [--root DIR]
  case_tool.py check  <案例目录或 case.json>
  case_tool.py render <案例目录或 case.json>      # 校验 + 写 tree.md 与 graph.canvas，并打印状态树
  case_tool.py index  [--root DIR]               # 重建 INDEX.md

案例库根目录：--root 参数 > 环境变量 PROBLEM_CASES_DIR > DEFAULT_ROOT。
"""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_ROOT = (
    "/Users/leiyuan/Library/Mobile Documents/iCloud~md~obsidian/Documents/"
    "freedom/investment_method/problem_cases"
)

QUERY_TYPES = {
    "feasible": "求可行解",
    "optimal": "求最优解",
    "posterior": "求估计/后验",
    "cause": "求原因",
    "policy": "求策略",
    "proof": "求证明",
}
CASE_STATUS = {
    "open": "进行中",
    "converging": "收敛中",
    "solved": "已解决",
    "parked": "暂停",
    "abandoned": "放弃",
}
NODE_KINDS = {"goal", "category", "candidate", "subgoal", "relax"}
KIND_LABEL = {"goal": "目标", "category": "类别", "candidate": "候选", "subgoal": "子目标", "relax": "放松约束"}
NODE_STATUS = ["open", "expanded", "pruned", "parked", "failed", "verified", "chosen"]
STATUS_LABEL = {
    "open": "待评估",
    "expanded": "已展开",
    "pruned": "淘汰",
    "parked": "搁置",
    "failed": "失败",
    "verified": "已验证",
    "chosen": "选定",
}
STATUS_MARK = {
    "open": "[ ]",
    "expanded": "[>]",
    "pruned": "[x]",
    "parked": "[~]",
    "failed": "[!]",
    "verified": "[v]",
    "chosen": "[*]",
}
CANVAS_COLOR = {"pruned": "1", "failed": "1", "parked": "3", "chosen": "4", "verified": "5"}
EVIDENCE_TYPES = {"fact", "computation", "test", "prediction", "preference"}
VERIF_RESULTS = {"pass", "fail", "pending"}
ARCH_STATUS = {"candidate", "active", "rejected"}
LIVE = {"open", "expanded", "verified", "chosen"}


# ---------------------------------------------------------------- 读写

def case_root(arg_root=None):
    return Path(arg_root or os.environ.get("PROBLEM_CASES_DIR") or DEFAULT_ROOT)


def resolve_case_file(p):
    p = Path(p)
    if p.is_dir():
        p = p / "case.json"
    if not p.exists():
        sys.exit(f"找不到案例文件：{p}")
    return p


def load_case(p):
    f = resolve_case_file(p)
    try:
        return f, json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"case.json 不是合法 JSON：{f}\n  第 {e.lineno} 行第 {e.colno} 列：{e.msg}")


def today():
    return datetime.date.today().isoformat()


def template(case_id, title, origin):
    d = today()
    return {
        "schema_version": 1,
        "id": case_id,
        "title": title,
        "status": "open",
        "origin": origin,
        "source": {"path": "", "note": ""},
        "created": d,
        "updated": d,
        "agent": "",
        "domain": [],
        "problem": {
            "user_words": "",
            "goal": "",
            "query_type": "feasible",
            "initial_state": [],
            "success_test": "",
        },
        "constraints": [],
        "archetypes": [],
        "nodes": [
            {
                "id": "N0",
                "label": title,
                "parent": None,
                "kind": "goal",
                "status": "open",
                "round": 1,
                "pruned_by": [],
                "parked_by": [],
                "evidence": [],
                "note": "",
                "history": [],
            }
        ],
        "links": [],
        "conflicts": [],
        "evidence": [],
        "verifications": [],
        "rounds": [],
        "solution": {"chosen": [], "alternatives": [], "summary": ""},
        "retro": {"lessons": [], "reusable_constraints": [], "archetype_fit": ""},
    }


# ---------------------------------------------------------------- 校验

def index_by_id(items):
    return {x.get("id"): x for x in items if isinstance(x, dict)}


def check(case):
    errors, warnings = [], []
    E, W = errors.append, warnings.append

    for key in ["id", "title", "status", "problem", "constraints", "archetypes", "nodes",
                "conflicts", "evidence", "verifications", "rounds", "solution"]:
        if key not in case:
            E(f"缺少字段 `{key}`")
    if errors:
        return errors, warnings

    if case["status"] not in CASE_STATUS:
        E(f"status `{case['status']}` 不在 {sorted(CASE_STATUS)}")
    qt = case["problem"].get("query_type")
    if qt not in QUERY_TYPES:
        E(f"problem.query_type `{qt}` 不在 {sorted(QUERY_TYPES)}")
    if not case["problem"].get("goal"):
        W("problem.goal 为空：先把目标写成一句话")
    if not case["problem"].get("success_test"):
        W("problem.success_test 为空：怎样算解决了，要在原问题里能检验")

    # ID 全局唯一
    seen = {}
    for group in ["constraints", "archetypes", "nodes", "conflicts", "evidence", "verifications"]:
        for x in case[group]:
            i = x.get("id")
            if not i:
                E(f"{group} 里有条目没有 id")
                continue
            if i in seen:
                E(f"id `{i}` 重复（{seen[i]} 与 {group}）")
            seen[i] = group

    C = index_by_id(case["constraints"])
    A = index_by_id(case["archetypes"])
    N = index_by_id(case["nodes"])
    K = case["conflicts"]
    EV = index_by_id(case["evidence"])
    V = case["verifications"]

    for c in case["constraints"]:
        if c.get("kind") not in {"hard", "soft"}:
            E(f"约束 {c.get('id')} 的 kind 必须是 hard 或 soft")
        if c.get("kind") == "hard" and not c.get("verified"):
            W(f"硬约束 {c['id']} 未经用户确认（verified=false），确认前不能用它淘汰候选")

    active = [a for a in case["archetypes"] if a.get("status") == "active"]
    for a in case["archetypes"]:
        if a.get("status") not in ARCH_STATUS:
            E(f"母题 {a.get('id')} 的 status 必须是 {sorted(ARCH_STATUS)}")
        if a.get("status") == "rejected" and not a.get("note"):
            E(f"母题 {a['id']} 已弃用，note 里要写弃用原因（哪个失效信号出现了）")
    if not active and len(case["nodes"]) > 1:
        W("没有 active 的近似母题：展开解空间前先选定母题与表示")

    for e in case["evidence"]:
        if e.get("type") not in EVIDENCE_TYPES:
            E(f"证据 {e.get('id')} 的 type 必须是 {sorted(EVIDENCE_TYPES)}")
        if not e.get("source"):
            W(f"证据 {e.get('id')} 没有 source")

    # 树结构
    roots = [n for n in case["nodes"] if n.get("parent") in (None, "")]
    if len(roots) != 1:
        E(f"解空间必须恰好有 1 个根节点，现在有 {len(roots)} 个")
    elif roots[0].get("kind") != "goal":
        E("根节点的 kind 必须是 goal")
    for n in case["nodes"]:
        nid = n.get("id")
        if n.get("parent") not in (None, "") and n["parent"] not in N:
            E(f"节点 {nid} 的 parent `{n['parent']}` 不存在")
        if n.get("kind") not in NODE_KINDS:
            E(f"节点 {nid} 的 kind `{n.get('kind')}` 不在 {sorted(NODE_KINDS)}")
        if n.get("status") not in NODE_STATUS:
            E(f"节点 {nid} 的 status `{n.get('status')}` 不在 {NODE_STATUS}")
        for ref in n.get("evidence", []):
            if ref not in EV:
                E(f"节点 {nid} 引用了不存在的证据 {ref}")
    for n in case["nodes"]:  # 环检测
        cur, steps = n, 0
        while cur and cur.get("parent") not in (None, "") and steps <= len(N):
            cur = N.get(cur["parent"])
            steps += 1
        if steps > len(N):
            E(f"节点 {n.get('id')} 的祖先链有环")

    def verifs(nid, result=None):
        return [v for v in V if v.get("target") == nid and (result is None or v.get("result") == result)]

    for n in case["nodes"]:
        nid, st = n.get("id"), n.get("status")
        if st == "pruned":
            refs = n.get("pruned_by", [])
            before = len(errors)
            if not refs:
                E(f"{nid} 被淘汰但 pruned_by 为空：淘汰必须指向违反的硬约束")
            for r in refs:
                c = C.get(r)
                if not c:
                    E(f"{nid} 的 pruned_by 引用了不存在的约束 {r}")
                elif c.get("kind") != "hard":
                    E(f"{nid} 被软偏好 {r} 淘汰：软偏好只能搁置（parked），不能淘汰")
                elif not c.get("verified"):
                    E(f"{nid} 被未确认的硬约束 {r} 淘汰：先请用户确认，或改为搁置")
            for r in n.get("evidence", []):
                if r in EV and not EV[r].get("verified"):
                    E(f"{nid} 的淘汰用了未核实的事实 {r}：未核实的事实不得用于淘汰，改为搁置")
            if len(errors) == before and n.get("kind") == "candidate" and not n.get("evidence"):
                W(f"{nid} 被淘汰但没附事实依据：确认它确实违反 {refs}（例如查到的条款、实测结果）")
        if st == "parked":
            refs = n.get("parked_by", [])
            for r in refs:
                if r not in C:
                    E(f"{nid} 的 parked_by 引用了不存在的约束 {r}")
            if not refs and not n.get("note"):
                E(f"{nid} 被搁置但没写原因（parked_by 或 note）")
        if st == "failed" and not verifs(nid, "fail") and not n.get("note"):
            E(f"{nid} 标为失败，但没有 result=fail 的验证记录，也没有 note")
        if st == "verified" and not verifs(nid, "pass"):
            E(f"{nid} 标为已验证，但没有 result=pass 的验证记录")
        if st == "chosen":
            if not verifs(nid, "pass"):
                msg = f"{nid} 已选定，但还没有在原问题里验证通过（result=pass）"
                (E if case["status"] == "solved" else W)(msg)

    for v in V:
        if v.get("target") not in N:
            E(f"验证 {v.get('id')} 的 target `{v.get('target')}` 不存在")
        if v.get("result") not in VERIF_RESULTS:
            E(f"验证 {v.get('id')} 的 result 必须是 {sorted(VERIF_RESULTS)}")
        for r in v.get("evidence", []):
            if r not in EV:
                E(f"验证 {v.get('id')} 引用了不存在的证据 {r}")

    covered = set()
    for k in K:
        for f in k.get("failed", []):
            if f not in N:
                E(f"冲突 {k.get('id')} 引用了不存在的节点 {f}")
            covered.add(f)
        if k.get("jump_to") and k["jump_to"] not in N:
            E(f"冲突 {k.get('id')} 的 jump_to `{k['jump_to']}` 不存在")
        if k.get("constraint") and k["constraint"] not in C:
            E(f"冲突 {k.get('id')} 的 constraint `{k['constraint']}` 不存在")
        if not k.get("common_cause"):
            E(f"冲突 {k.get('id')} 没写 common_cause")

    for lk in case.get("links", []):
        if lk.get("from") not in N or lk.get("to") not in N:
            E(f"links 里有不存在的节点：{lk}")

    # 方法规则提醒
    children = {}
    for n in case["nodes"]:
        children.setdefault(n.get("parent"), []).append(n)
    for pid, kids in children.items():
        failed = [k["id"] for k in kids if k.get("status") == "failed" and k["id"] not in covered]
        if len(failed) >= 2:
            W(f"规则·跳级回溯：{pid} 下已有 {len(failed)} 个失败（{', '.join(failed)}）还没提取共同原因。"
              "先写一条 conflict，跳到上一层，不要再试同层的下一个")

    non_goal = [n for n in case["nodes"] if n.get("kind") != "goal"]
    live = [n for n in non_goal if n.get("status") in LIVE]
    parked = [n["id"] for n in non_goal if n.get("status") == "parked"]
    if non_goal and not live and parked:
        W("规则·重审搁置：所有可行候选都已出局。宣布无解或放弃前，必须逐个重审搁置项："
          + ", ".join(parked))
    if case["status"] == "abandoned" and parked:
        W("规则·重审搁置：案例标为放弃，但仍有搁置项未重审：" + ", ".join(parked))

    sol = case["solution"]
    if case["status"] == "solved":
        if not sol.get("chosen"):
            E("status=solved 但 solution.chosen 为空")
        for c in sol.get("chosen", []):
            if c not in N:
                E(f"solution.chosen 引用了不存在的节点 {c}")
            elif N[c].get("status") != "chosen":
                E(f"solution.chosen 里的 {c} 节点状态不是 chosen")
        if not case.get("retro", {}).get("lessons"):
            W("已解决但 retro.lessons 为空：结案时写下可复用的经验")

    last = 0
    for r in case["rounds"]:
        n = r.get("n")
        if not isinstance(n, int):
            E(f"rounds 里的 n 必须是整数：{r}")
            continue
        if n <= last:
            E(f"rounds 的轮次必须递增（{last} 之后出现 {n}）")
        last = n
    return errors, warnings


# ---------------------------------------------------------------- 指标

def metrics(case):
    N = index_by_id(case["nodes"])
    rounds = case["rounds"]
    attempts = [r["real_world_attempt"] for r in rounds if r.get("real_world_attempt")]
    counts = {s: 0 for s in NODE_STATUS}
    for n in case["nodes"]:
        if n.get("status") in counts:
            counts[n["status"]] += 1

    def rounds_of(n):
        rs = [n.get("round")] + [h.get("round") for h in n.get("history", [])]
        return [x for x in rs if isinstance(x, int)]

    first_seen, chosen_at = None, None
    for cid in case["solution"].get("chosen", []):
        n = N.get(cid)
        if not n:
            continue
        rs = rounds_of(n)
        if rs:
            first_seen = min(rs) if first_seen is None else min(first_seen, min(rs))
        for h in n.get("history", []):
            if h.get("status") == "chosen" and isinstance(h.get("round"), int):
                chosen_at = h["round"] if chosen_at is None else min(chosen_at, h["round"])
    reopened = 0
    for n in case["nodes"]:
        seq = [h.get("status") for h in n.get("history", [])]
        if "parked" in seq and any(s != "parked" for s in seq[seq.index("parked") + 1:]):
            reopened += 1
    return {
        "记录轮数": len(rounds),
        "用户纠正次数": sum(1 for r in rounds if r.get("correction")),
        "现实尝试次数": len(attempts),
        "现实尝试失败": sum(1 for a in attempts if a.get("result") == "fail"),
        "节点数": len(case["nodes"]),
        **{f"节点·{STATUS_LABEL[s]}": counts[s] for s in NODE_STATUS},
        "冲突核数": len(case["conflicts"]),
        "母题更换次数": sum(1 for a in case["archetypes"] if a.get("status") == "rejected"),
        "搁置后重新启用": reopened,
        "解首次出现轮次": first_seen,
        "解选定轮次": chosen_at,
    }


# ---------------------------------------------------------------- 渲染

def node_reason(n, case):
    C = index_by_id(case["constraints"])
    st = n.get("status")

    def ctext(ids):
        return "；".join(f"{i} {C[i]['text']}" if i in C else i for i in ids)

    vs = [v for v in case["verifications"] if v.get("target") == n.get("id")]
    if st == "pruned":
        return ctext(n.get("pruned_by", []))
    if st == "parked":
        parts = [ctext(n.get("parked_by", []))] if n.get("parked_by") else []
        if n.get("note"):
            parts.append(n["note"])
        return "；".join(parts)
    if st == "failed":
        f = [v for v in vs if v.get("result") == "fail"]
        return f"{f[-1]['id']} {f[-1].get('method', '')}" if f else n.get("note", "")
    if st in ("verified", "chosen"):
        p = [v for v in vs if v.get("result") == "pass"]
        pend = [v for v in vs if v.get("result") == "pending"]
        bits = [f"{v['id']} {v.get('method', '')}" for v in p]
        bits += [f"{v['id']} 待验证：{v.get('method', '')}" for v in pend]
        return "；".join(bits) if bits else "尚未验证"
    return n.get("note", "")


def tree_lines(case):
    kids = {}
    for n in case["nodes"]:
        kids.setdefault(n.get("parent") or None, []).append(n)
    jumps = {}
    for k in case["conflicts"]:
        for f in k.get("failed", []):
            jumps[f] = k
    out = []

    def walk(n, depth):
        reason = node_reason(n, case)
        tag = STATUS_LABEL.get(n.get("status"), n.get("status"))
        kind = "" if n.get("kind") in ("candidate", "goal") else f"〔{KIND_LABEL.get(n.get('kind'), '')}〕"
        line = f"{'  ' * depth}{STATUS_MARK.get(n.get('status'), '[?]')} {n['id']} {kind}{n.get('label', '')} —— {tag}"
        if reason:
            line += f"：{reason}"
        if n["id"] in jumps:
            k = jumps[n["id"]]
            line += f"  ⟶ {k['id']} 共同原因「{k['common_cause']}」，跳到 {k.get('jump_to', '?')}"
        out.append(line)
        for c in kids.get(n["id"], []):
            walk(c, depth + 1)

    for r in kids.get(None, []):
        walk(r, 0)
    return out


def md_cell(x):
    if isinstance(x, list):
        x = "；".join(str(i) for i in x)
    return str(x if x not in (None, "") else "—").replace("|", "\\|").replace("\n", " ")


def render_md(case, errors, warnings):
    p = case["problem"]
    L = [f"# {case['title']}", ""]
    L.append(f"> 自动生成，不要手改；真源是同目录的 `case.json`。案例 `{case['id']}`，"
             f"{CASE_STATUS.get(case['status'], case['status'])}，"
             f"{QUERY_TYPES.get(p.get('query_type'), p.get('query_type'))}，来源 {case.get('origin', '')}，"
             f"更新 {case.get('updated', '')}。")
    if case.get("source", {}).get("path"):
        L.append(f"> 原始材料：`{case['source']['path']}` {case['source'].get('note', '')}")
    L += ["", "## 问题", ""]
    if p.get("user_words"):
        L += [f"> {p['user_words']}", ""]
    L.append(f"- 目标：{p.get('goal') or '—'}")
    L.append(f"- 成功检验：{p.get('success_test') or '—'}")
    for s in p.get("initial_state", []):
        L.append(f"- 初始状态：{s}")
    L += ["", "## 约束", "", "| ID | 约束 | 硬/软 | 已确认 | 来源 |", "|---|---|---|---|---|"]
    for c in case["constraints"]:
        src = c.get("source", "")
        if c.get("quote"):
            src += f"：「{c['quote']}」"
        L.append(f"| {c['id']} | {md_cell(c.get('text'))} | {'硬' if c.get('kind') == 'hard' else '软'} | "
                 f"{'是' if c.get('verified') else '否'} | {md_cell(src)} |")
    L += ["", "## 近似母题", "", "| ID | 母题 | 状态 | 映射 | 表示 | 基本解法 | 适用假设 | 失效信号 |",
          "|---|---|---|---|---|---|---|---|"]
    for a in case["archetypes"]:
        L.append(f"| {a['id']} | {md_cell(a.get('name'))} | {md_cell(a.get('status'))} | {md_cell(a.get('mapping'))} | "
                 f"{md_cell(a.get('representation'))} | {md_cell(a.get('method'))} | {md_cell(a.get('assumptions'))} | "
                 f"{md_cell(a.get('failure_signals'))} |")
        if a.get("note"):
            L.append(f"| | ↳ {md_cell(a['note'])} | | | | | | |")
    L += ["", "## 解空间", "", "```text"] + tree_lines(case) + ["```", "",
          "图例：[*] 选定　[v] 已验证　[>] 已展开　[ ] 待评估　[~] 搁置（软偏好或依据未核实，可重审）　"
          "[x] 淘汰（违反已确认的硬约束）　[!] 失败（现实尝试或验证失败）", ""]
    if case["conflicts"]:
        L += ["## 冲突核", "", "| ID | 一起失败的节点 | 共同原因 | 对应约束 | 跳到 | 轮次 |", "|---|---|---|---|---|---|"]
        for k in case["conflicts"]:
            L.append(f"| {k['id']} | {md_cell(k.get('failed'))} | {md_cell(k.get('common_cause'))} | "
                     f"{md_cell(k.get('constraint'))} | {md_cell(k.get('jump_to'))} | {md_cell(k.get('round'))} |")
        L.append("")
    if case["verifications"]:
        L += ["## 原问题里的验证", "", "| ID | 对象 | 方法 | 结果 | 日期 | 说明 |", "|---|---|---|---|---|---|"]
        for v in case["verifications"]:
            L.append(f"| {v['id']} | {md_cell(v.get('target'))} | {md_cell(v.get('method'))} | {md_cell(v.get('result'))} | "
                     f"{md_cell(v.get('date'))} | {md_cell(v.get('note'))} |")
        L.append("")
    if case["evidence"]:
        L += ["## 证据", "", "| ID | 断言 | 类型 | 已核实 | 来源 |", "|---|---|---|---|---|"]
        for e in case["evidence"]:
            L.append(f"| {e['id']} | {md_cell(e.get('claim'))} | {md_cell(e.get('type'))} | "
                     f"{'是' if e.get('verified') else '否'} | {md_cell(e.get('source'))} |")
        L.append("")
    sol = case["solution"]
    L += ["## 方案", "", f"- 选定：{md_cell(sol.get('chosen'))}", f"- 备选：{md_cell(sol.get('alternatives'))}",
          f"- 说明：{sol.get('summary') or '—'}", ""]
    if case["rounds"]:
        L += ["## 探索过程", "", "| 轮 | 用户 | 纠正 | 本轮动作 | 现实尝试 |", "|---|---|---|---|---|"]
        for r in case["rounds"]:
            a = r.get("real_world_attempt")
            att = f"{a.get('target')}：{a.get('result')}" if a else "—"
            L.append(f"| {r.get('n')} | {md_cell(r.get('user'))} | {'是' if r.get('correction') else ''} | "
                     f"{md_cell(r.get('actions'))} | {md_cell(att)} |")
        L.append("")
    retro = case.get("retro", {})
    if any(retro.get(k) for k in ("lessons", "reusable_constraints", "archetype_fit")):
        L += ["## 复盘", ""]
        for x in retro.get("lessons", []):
            L.append(f"- 经验：{x}")
        for x in retro.get("reusable_constraints", []):
            L.append(f"- 可复用的约束知识：{x}")
        if retro.get("archetype_fit"):
            L.append(f"- 母题是否合适：{retro['archetype_fit']}")
        L.append("")
    L += ["## 指标", "", "| 指标 | 值 |", "|---|---|"]
    for k, v in metrics(case).items():
        L.append(f"| {k} | {md_cell(v)} |")
    L += ["", "## 校验", ""]
    if not errors and not warnings:
        L.append("全部通过。")
    L += [f"- 错误：{e}" for e in errors] + [f"- 提醒：{w}" for w in warnings]
    return "\n".join(L) + "\n"


def render_canvas(case):
    kids = {}
    for n in case["nodes"]:
        kids.setdefault(n.get("parent") or None, []).append(n)
    W_, H_, DX, DY = 340, 120, 420, 150
    pos, order = {}, [0]

    def place(n, depth):
        cs = kids.get(n["id"], [])
        if not cs:
            y = order[0] * DY
            order[0] += 1
        else:
            ys = [place(c, depth + 1) for c in cs]
            y = (ys[0] + ys[-1]) / 2
        pos[n["id"]] = (depth * DX, y)
        return y

    for r in kids.get(None, []):
        place(r, 0)
    nodes, edges = [], []
    for n in case["nodes"]:
        if n["id"] not in pos:
            continue
        x, y = pos[n["id"]]
        text = f"**{n['id']} {n.get('label', '')}**\n{STATUS_LABEL.get(n.get('status'), '')}"
        reason = node_reason(n, case)
        if reason:
            text += f"：{reason}"
        cn = {"id": n["id"], "type": "text", "text": text, "x": int(x), "y": int(y), "width": W_, "height": H_}
        if n.get("status") in CANVAS_COLOR:
            cn["color"] = CANVAS_COLOR[n["status"]]
        nodes.append(cn)
        if n.get("parent") in pos:
            edges.append({"id": f"e-{n['parent']}-{n['id']}", "fromNode": n["parent"], "fromSide": "right",
                          "toNode": n["id"], "toSide": "left"})
    for i, lk in enumerate(case.get("links", [])):
        if lk.get("from") in pos and lk.get("to") in pos:
            edges.append({"id": f"l{i}", "fromNode": lk["from"], "fromSide": "bottom", "toNode": lk["to"],
                          "toSide": "top", "label": lk.get("type", ""), "color": "6"})
    for k in case["conflicts"]:
        if k.get("jump_to") in pos:
            for f in k.get("failed", []):
                if f in pos:
                    edges.append({"id": f"{k['id']}-{f}", "fromNode": f, "fromSide": "bottom",
                                  "toNode": k["jump_to"], "toSide": "top",
                                  "label": f"{k['id']} {k.get('common_cause', '')}", "color": "2"})
    ctext = "**约束**\n" + "\n".join(
        f"- {c['id']} {'硬' if c.get('kind') == 'hard' else '软'}{'' if c.get('verified') else '（未确认）'}：{c.get('text', '')}"
        for c in case["constraints"])
    nodes.append({"id": "constraints", "type": "text", "text": ctext, "x": -DX - 40, "y": 0,
                  "width": 380, "height": max(160, 34 * (len(case["constraints"]) + 1))})
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------- 命令

def cmd_new(args):
    root = case_root(args.root)
    slug = re.sub(r"[\s/\\]+", "-", args.slug.strip()).strip("-")
    if not slug:
        sys.exit("slug 不能为空")
    d = root / f"{today()}_{slug}"
    if d.exists():
        sys.exit(f"案例已存在：{d}")
    d.mkdir(parents=True)
    (d / "case.json").write_text(json.dumps(template(d.name, args.title, args.origin), ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print(d / "case.json")


def cmd_check(args):
    _, case = load_case(args.case)
    errors, warnings = check(case)
    for e in errors:
        print(f"错误：{e}")
    for w in warnings:
        print(f"提醒：{w}")
    if not errors and not warnings:
        print("全部通过。")
    sys.exit(1 if errors else 0)


def cmd_render(args):
    f, case = load_case(args.case)
    errors, warnings = check(case)
    (f.parent / "tree.md").write_text(render_md(case, errors, warnings), encoding="utf-8")
    (f.parent / "graph.canvas").write_text(json.dumps(render_canvas(case), ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    print("\n".join(tree_lines(case)))
    print()
    for e in errors:
        print(f"错误：{e}")
    for w in warnings:
        print(f"提醒：{w}")
    print(f"已写入：{f.parent / 'tree.md'}，{f.parent / 'graph.canvas'}")
    sys.exit(1 if errors else 0)


def cmd_index(args):
    root = case_root(args.root)
    rows = []
    for f in sorted(root.glob("*/case.json")):
        try:
            case = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rows.append((f.parent.name, "（case.json 无法解析）", "", "", "", "", "", "", ""))
            continue
        m = metrics(case)
        errors, _ = check(case)
        arch = "；".join(a.get("name", "") for a in case.get("archetypes", []) if a.get("status") == "active")
        rows.append((
            f"[{case.get('id', f.parent.name)}]({f.parent.name}/tree.md)",
            case.get("title", ""),
            CASE_STATUS.get(case.get("status"), case.get("status", "")),
            QUERY_TYPES.get(case.get("problem", {}).get("query_type"), ""),
            arch,
            "；".join(case.get("domain", [])),
            m["记录轮数"],
            m["用户纠正次数"],
            "有" if errors else "",
        ))
    L = ["# 问题结构案例库", "",
         "> 由 `case_tool.py index` 自动生成。每个案例的真源是各自目录下的 `case.json`，`tree.md` 与 `graph.canvas` 由 `render` 生成。",
         "", f"共 {len(rows)} 个案例。", "",
         "| 案例 | 标题 | 状态 | 查询类型 | 近似母题 | 领域 | 记录轮数 | 用户纠正 | 校验错误 |",
         "|---|---|---|---|---|---|---|---|---|"]
    L += ["| " + " | ".join(md_cell(x) for x in r) + " |" for r in rows]
    root.mkdir(parents=True, exist_ok=True)
    (root / "INDEX.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(root / "INDEX.md")


def main():
    ap = argparse.ArgumentParser(description="problem-as-structure 案例工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="新建案例")
    p.add_argument("--slug", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--origin", default="live", choices=["live", "retro"])
    p.add_argument("--root")
    p.set_defaults(func=cmd_new)
    for name, fn in (("check", cmd_check), ("render", cmd_render)):
        p = sub.add_parser(name)
        p.add_argument("case")
        p.set_defaults(func=fn)
    p = sub.add_parser("index", help="重建 INDEX.md")
    p.add_argument("--root")
    p.set_defaults(func=cmd_index)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
