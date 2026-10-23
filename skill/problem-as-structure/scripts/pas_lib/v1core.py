#!/usr/bin/env python3
"""v1 一致性内核：原样保留 v1 case_tool.py 的校验、指标与渲染逻辑（只去掉命令入口）。

v2 把每个案例转成 v1 形状的视图后调用这里，保证 v1 已有规则的行为和文字逐字不变。
不要在这里加 v2 的新规则；新规则写在 core_checks.py 和工作结构定义里。

以下是 v1 原文档：
problem-as-structure 案例工具：新建、校验、渲染、索引。只用 Python 标准库。

用法：
  case_tool.py new --slug itin-credit --title "用 ITIN 办美国信用卡" [--origin retro] [--root DIR]
  case_tool.py check  <案例目录或 case.json>
  case_tool.py render <案例目录或 case.json>      # 校验 + 写 tree.md、graph.canvas 与 progress.html，并打印状态树
  case_tool.py html   <案例目录或 case.json>      # 只写 progress.html（离线单文件进展面板）
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
# 约束的依据：谁说了算
BASIS = {"value": "价值/偏好", "own_fact": "用户自身处境", "world_fact": "外部世界事实"}
# 分歧
DIS_BASIS = {"value": "价值/偏好", "own_fact": "用户自身处境", "world_fact": "外部世界事实", "method": "做法"}
DIS_RESOLUTION = {
    "pending": "待检验",
    "user_right": "用户对",
    "ai_right": "AI 对",
    "both_partly": "各对一部分",
    "user_decides": "用户决定（未验证或属价值判断）",
}
PROPOSERS = {"user", "ai"}
# 进展面板：阶段
CLAIM_STATUS = {"current": "有效", "superseded": "已取代", "withdrawn": "已撤回", "refuted": "已证伪"}
EDGE_TYPES = {"conclusion": "依赖结论", "method": "继承方法", "cites": "只引用"}
CLAIM_KINDS = {"create", "fix_reason", "narrow_statement", "clarify_assumption", "cite_update", "withdraw"}
STAGE_STATUS = {"done": "完成", "partial": "部分完成", "active": "进行中", "todo": "未开始", "later": "推迟"}
STAGE_MARK = {"done": "✓", "partial": "◐", "active": "▶", "todo": "○", "later": "…"}
APPROVAL_WORDS = re.compile(r"满意|同意|认可|觉得(可以|行|好)|点头|approve|approval|happy|satisf", re.I)


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
                "proposed_by": "user",
                "pruned_by": [],
                "parked_by": [],
                "evidence": [],
                "note": "",
                "history": [],
            }
        ],
        "links": [],
        "conflicts": [],
        "disagreements": [],
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
    elif APPROVAL_WORDS.search(case["problem"]["success_test"]):
        W("规则·验收接现实：success_test 看起来是'用户满意/同意'。成功检验必须是现实里能观察到的结果，"
          "否则用户的判断就是天花板")

    # ID 全局唯一
    seen = {}
    for group in ["constraints", "archetypes", "nodes", "conflicts", "evidence", "verifications", "disagreements", "claims"]:
        for x in case.get(group, []):
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

    EV0 = index_by_id(case["evidence"])

    def world_fact_backed(c):
        """外部世界事实类约束：要有已核实的证据，用户说了不算。"""
        return any(EV0.get(r, {}).get("verified") for r in c.get("evidence", []))

    for c in case["constraints"]:
        cid = c.get("id")
        if c.get("kind") not in {"hard", "soft"}:
            E(f"约束 {cid} 的 kind 必须是 hard 或 soft")
        b = c.get("basis")
        if b is None:
            W(f"约束 {cid} 没标 basis（value / own_fact / world_fact）：先分清这是用户的偏好、用户自身处境，还是对外部世界的判断")
        elif b not in BASIS:
            E(f"约束 {cid} 的 basis `{b}` 不在 {sorted(BASIS)}")
        for r in c.get("evidence", []):
            if r not in EV0:
                E(f"约束 {cid} 引用了不存在的证据 {r}")
        if b == "world_fact" and c.get("kind") == "soft":
            W(f"约束 {cid} 是外部世界事实，却标成 soft：事实不是偏好，要么是硬约束，要么改成一条证据")
        if c.get("kind") == "hard" and not c.get("verified"):
            W(f"硬约束 {cid} 未经用户确认（verified=false），确认前不能用它淘汰候选")
        if b == "world_fact" and c.get("kind") == "hard" and not world_fact_backed(c):
            W(f"硬约束 {cid} 是对外部世界的判断，但没有已核实的证据：用户说了不等于事实成立，核实前不能用它淘汰候选")

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
        if n.get("proposed_by") not in (None, "") and n["proposed_by"] not in PROPOSERS:
            E(f"节点 {nid} 的 proposed_by `{n['proposed_by']}` 必须是 user 或 ai")
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

    OUT = {"pruned", "failed"}

    def check_park_reference(n, pr):
        """软约束是相对的：检查参照对象是否可行，以及被搁置者是否已是可行集合里该维度最好的。"""
        nid = n.get("id")
        measure = pr.get("measure")
        direction = pr.get("direction", "lower")
        if direction not in ("lower", "higher"):
            E(f"{nid} 的 park_reference.direction 必须是 lower（越低越好）或 higher（越高越好）")
            return
        comp = pr.get("compared_to", [])
        for x in comp:
            if x not in N:
                E(f"{nid} 的 park_reference.compared_to 引用了不存在的节点 {x}")
        if not measure:
            W(f"{nid} 的 park_reference 没写 measure（成本、时间、精力、风险……）")
        if not comp and not pr.get("external"):
            W(f"{nid} 的 park_reference 既没有台账里的参照节点（compared_to），也没写台账外的参照（external）")
        known = [x for x in comp if x in N]
        if known and all(N[x].get("status") in OUT for x in known):
            W(f"规则·参照失效：{nid} 因{measure or '某个维度'}比 {', '.join(known)} 差而被搁置，但这些参照都已出局（淘汰或失败）。"
              "在当前可行集合里重新比较；差出来的部分可能是约束的价格，不是方案的价格")
        if not measure:
            return
        mine = n.get("attrs", {}).get(measure)
        if not isinstance(mine, (int, float)):
            return
        rivals = [s for s in case["nodes"] if s.get("id") != nid and s.get("kind") in ("candidate", "relax")
                  and s.get("status") not in OUT and isinstance(s.get("attrs", {}).get(measure), (int, float))]
        better = [s["id"] for s in rivals
                  if (s["attrs"][measure] < mine if direction == "lower" else s["attrs"][measure] > mine)]
        if not better:
            scope = f"（参与比较的可行候选：{', '.join(s['id'] for s in rivals)}）" if rivals else "（没有其他标了该维度的可行候选）"
            W(f"规则·可行集最优：{nid} 在当前可行候选里 {measure}={mine} 已是最好，却因为它被搁置{scope}。"
              "把它重新摆出来，说明这是约束的代价，并列出放松哪条约束能换来更好的结果")

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
                elif c.get("basis") == "world_fact" and not world_fact_backed(c):
                    E(f"{nid} 被外部世界事实 {r} 淘汰，但 {r} 没有已核实的证据：用户说了不等于事实成立，核实前改为搁置")
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
            soft = [r for r in refs if C.get(r, {}).get("kind") == "soft"]
            pr = n.get("park_reference")
            if soft and not pr:
                W(f"{nid} 因软偏好 {soft} 被搁置，但没写 park_reference：'太贵、太慢、太麻烦'是和谁比？"
                  "写下比较维度和参照对象（见 references/soft_constraints.md）")
            if pr:
                check_park_reference(n, pr)
        if st == "failed" and not verifs(nid, "fail") and not n.get("note"):
            E(f"{nid} 标为失败，但没有 result=fail 的验证记录，也没有 note")
        if st == "verified" and not verifs(nid, "pass"):
            E(f"{nid} 标为已验证，但没有 result=pass 的验证记录")
        if st == "chosen":
            if not verifs(nid, "pass"):
                msg = f"{nid} 已选定，但还没有在原问题里验证通过（result=pass）"
                (E if case["status"] == "solved" else W)(msg)
            sibs = [s for s in case["nodes"] if s.get("parent") == n.get("parent") and s.get("id") != nid]
            if not any(s.get("status") != "open" for s in sibs):
                who = "用户提出的" if n.get("proposed_by") == "user" else ""
                W(f"规则·对照：{who}方案 {nid} 被选定时，同层没有任何经过评估的对照候选。"
                  "至少再展开并评估一个替代做法，否则提出者的视野就是上限")

    CL = index_by_id(case.get("claims") or [])
    for v in V:
        if v.get("target") not in N and v.get("target") not in CL:
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
        f, to = lk.get("from"), lk.get("to")
        if (f in CL) != (to in CL) or (f not in N and f not in CL) or (to not in N and to not in CL):
            E(f"links 里有不存在的节点或论断（论断只能连论断）：{lk}")
        if "edge" in lk and lk["edge"] not in EDGE_TYPES:
            E(f"links 的 edge `{lk['edge']}` 不在 {list(EDGE_TYPES)}：{lk}")

    VI = index_by_id(V)
    for d in case.get("disagreements", []):
        did, b, res = d.get("id"), d.get("basis"), d.get("resolution")
        if b not in DIS_BASIS:
            E(f"分歧 {did} 的 basis `{b}` 不在 {sorted(DIS_BASIS)}")
        if res not in DIS_RESOLUTION:
            E(f"分歧 {did} 的 resolution `{res}` 不在 {sorted(DIS_RESOLUTION)}")
        if not d.get("user_position") or not d.get("ai_position"):
            E(f"分歧 {did} 要同时写 user_position 和 ai_position")
        about = d.get("about")
        if about and about not in N and about not in C:
            E(f"分歧 {did} 的 about `{about}` 不是已有的节点或约束")
        v = d.get("verification")
        if v and v not in VI:
            E(f"分歧 {did} 引用了不存在的验证 {v}")
        if b == "value" and res in ("user_right", "ai_right", "both_partly"):
            W(f"分歧 {did} 属于价值/偏好，没有对错：resolution 应为 user_decides")
        if b in ("world_fact", "method"):
            if res in ("user_right", "ai_right", "both_partly"):
                if not v or VI.get(v, {}).get("result") not in ("pass", "fail"):
                    E(f"分歧 {did} 判了 {res}，但没有挂一条已出结果（pass/fail）的验证：对错要由原问题里的检验来判")
            elif res == "user_decides":
                W(f"分歧 {did}：关于{DIS_BASIS[b]}，按用户意见执行但没有验证。把能分出对错的检验排进下一步")
            elif res == "pending" and not d.get("test"):
                W(f"分歧 {did} 待检验，但没写 test：写下用什么检验来分出对错")

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

    check_progress(case, N, C, E)
    check_claims(case, N, C, EV, E, W)
    return errors, warnings


def check_progress(case, N, C, E):
    """进展面板用的可选字段：stages、pending、running。缺省即不检查。"""
    S = {}
    stages = case.get("stages")
    if stages is not None:
        if not isinstance(stages, list):
            E("stages 必须是列表")
            stages = []
        for s in stages:
            if not isinstance(s, dict) or not s.get("id"):
                E("stages 里有条目没有 id")
                continue
            if s["id"] in S:
                E(f"阶段 id `{s['id']}` 重复")
            S[s["id"]] = s
        for sid, s in S.items():
            if not s.get("label"):
                E(f"阶段 {sid} 没有 label")
            if s.get("status") not in STAGE_STATUS:
                E(f"阶段 {sid} 的 status `{s.get('status')}` 不在 {list(STAGE_STATUS)}")
            outs = s.get("outputs", [])
            if not isinstance(outs, list) or not all(isinstance(x, str) for x in outs):
                E(f"阶段 {sid} 的 outputs 必须是字符串列表")
            if not isinstance(s.get("missing", ""), str):
                E(f"阶段 {sid} 的 missing 必须是字符串")
            deps = s.get("depends_on", [])
            if not isinstance(deps, list):
                E(f"阶段 {sid} 的 depends_on 必须是列表")
            else:
                for d in deps:
                    if d not in S:
                        E(f"阶段 {sid} 的 depends_on 引用了不存在的阶段 {d}")
            ns = s.get("nodes", [])
            if not isinstance(ns, list):
                E(f"阶段 {sid} 的 nodes 必须是列表")
            else:
                for x in ns:
                    if x not in N:
                        E(f"阶段 {sid} 的 nodes 引用了不存在的节点 {x}")
        state = {}

        def visit(sid):
            if state.get(sid) == 1:
                return True
            if state.get(sid) == 2:
                return False
            state[sid] = 1
            deps = S[sid].get("depends_on", [])
            cyc = isinstance(deps, list) and any(d in S and visit(d) for d in deps)
            state[sid] = 2
            return cyc

        for sid in S:
            if sid not in state and visit(sid):
                E(f"阶段 {sid} 的 depends_on 有环")

    pending = case.get("pending")
    if pending is not None:
        if not isinstance(pending, list):
            E("pending 必须是列表")
            pending = []
        seen = set()
        for p in pending:
            if not isinstance(p, dict) or not p.get("id"):
                E("pending 里有条目没有 id")
                continue
            pid = p["id"]
            if pid in seen:
                E(f"待决事项 id `{pid}` 重复")
            seen.add(pid)
            if not p.get("question"):
                E(f"待决事项 {pid} 没有 question")
            about = p.get("about", [])
            if isinstance(about, str):
                about = [about]
            if not isinstance(about, list):
                E(f"待决事项 {pid} 的 about 必须是 ID 列表")
                about = []
            for a in about:
                if a not in N and a not in C and a not in S:
                    E(f"待决事项 {pid} 的 about `{a}` 不是已有的节点、约束或阶段")
            if "since_round" in p and not isinstance(p["since_round"], int):
                E(f"待决事项 {pid} 的 since_round 必须是整数")

    running = case.get("running")
    if running is not None:
        if not isinstance(running, list):
            E("running 必须是列表")
            running = []
        for r in running:
            if not isinstance(r, dict) or not r.get("label"):
                E("running 里有条目没有 label")
                continue
            for k in ("report_path", "started"):
                if k in r and not isinstance(r[k], str):
                    E(f"后台任务「{r['label']}」的 {k} 必须是字符串")


# ---------------------------------------------------------------- 论断台账（可选）

def claim_edges(case):
    """论断之间的依赖边：links 里 type=depends_on 且两端都是论断。edge 缺省按 conclusion（保守）。"""
    CL = index_by_id(case.get("claims") or [])
    out = []
    for lk in case.get("links", []):
        if lk.get("type") == "depends_on" and lk.get("from") in CL and lk.get("to") in CL:
            out.append((lk["from"], lk["to"], lk.get("edge", "conclusion")))
    return out


def claim_proposer(cl):
    """论断的提出者：claims[].proposed_by，缺省为 ai。"""
    return str(cl.get("proposed_by") or "ai").strip().lower()


def independent_ok(cl, v):
    """independent=true 只有在验证写明检验者（by），且检验者不是论断的提出者时才承认。
    同一个 agent 自己核查自己，哪怕标了 independent，也不算独立检验。"""
    by = str(v.get("by") or "").strip().lower()
    return v.get("independent") is True and bool(by) and by != claim_proposer(cl)


def claim_grade(case, cl):
    """等级由验证记录计算，不手填。V0 无通过的验证；V1 有通过；V2 通过且可复跑（rerun）；
    V3 通过且检验者独立于提出者（independent=true，写明 by，且 by 不是提出者）。
    coverage.weaker_than_claim 为真时降一级。"""
    vs = [v for v in case["verifications"] if v.get("target") == cl.get("id") and v.get("result") == "pass"]
    g = 0
    if vs:
        g = 1
        if any(v.get("rerun") for v in vs):
            g = 2
        if any(independent_ok(cl, v) for v in vs):
            g = 3
    if (cl.get("coverage") or {}).get("weaker_than_claim") and g > 0:
        g -= 1
    return g


def claim_alerts(case):
    """上游被撤回/证伪：沿 conclusion、method 边传递连带；cites 边只提醒改引用，不再往下传。"""
    CL = index_by_id(case.get("claims") or [])
    edges = claim_edges(case)
    down = {}
    for f, to, e in edges:
        down.setdefault(to, []).append((f, e))
    rules, notes = [], []
    for cid, c in CL.items():
        st = c.get("status", "current")
        if st in ("withdrawn", "refuted"):
            seen, stack = set(), [cid]
            while stack:
                u = stack.pop()
                for f, e in down.get(u, []):
                    if e == "cites" or f in seen:
                        continue
                    seen.add(f)
                    if CL[f].get("status", "current") in ("withdrawn", "refuted", "superseded"):
                        continue
                    rules.append((f, cid, u, e))
                    stack.append(f)
    for f, to, e in edges:
        st = CL[to].get("status", "current")
        if CL[f].get("status", "current") in ("withdrawn", "refuted", "superseded"):
            continue
        if e == "cites" and st in ("withdrawn", "refuted", "superseded"):
            notes.append((f, to, e, st))
        elif e != "cites" and st == "superseded":
            notes.append((f, to, e, st))
    return rules, notes


def check_claims(case, N, C, EV, E, W):
    claims = case.get("claims")
    if claims is None:
        return
    if not isinstance(claims, list):
        E("claims 必须是列表")
        return
    CL = index_by_id(claims)
    S = index_by_id(case.get("stages") or [])
    for c in claims:
        cid = c.get("id")
        if not cid:
            continue
        if not c.get("statement"):
            E(f"论断 {cid} 没有 statement")
        st = c.get("status", "current")
        if st not in CLAIM_STATUS:
            E(f"论断 {cid} 的 status `{st}` 不在 {list(CLAIM_STATUS)}")
        if c.get("supersedes") and c["supersedes"] not in CL:
            E(f"论断 {cid} 的 supersedes `{c['supersedes']}` 不存在")
        if st == "current" and c.get("withdrawal"):
            E(f"论断 {cid} 状态是有效，却带有 withdrawal")
        if st == "withdrawn" and (c.get("withdrawal") or {}).get("scope") not in ("proof", "statement"):
            E(f"论断 {cid} 已撤回，withdrawal.scope 必须是 proof（理由失效）或 statement（陈述本身作废）")
        for a in c.get("about", []) or []:
            if a not in N and a not in C and a not in S:
                E(f"论断 {cid} 的 about `{a}` 不是已有的节点、约束或阶段")
        for r in c.get("evidence", []) or []:
            if r not in EV:
                E(f"论断 {cid} 引用了不存在的证据 {r}")
        cov = c.get("coverage")
        if cov is not None and (not isinstance(cov, dict) or not isinstance(cov.get("not_covered", []), list)):
            E(f"论断 {cid} 的 coverage 必须是 {{checked, not_covered: [..], weaker_than_claim}}")
        for h in c.get("history", []) or []:
            if h.get("kind") not in CLAIM_KINDS:
                E(f"论断 {cid} 的 history.kind `{h.get('kind')}` 不在 {sorted(CLAIM_KINDS)}")
        for v in case["verifications"]:
            if v.get("target") == cid and v.get("independent") is True and not independent_ok(c, v):
                why = "没写检验者 by" if not v.get("by") else f"检验者 `{v.get('by')}` 就是提出者"
                W(f"提醒·独立：验证 {v.get('id')} 标了 independent，但{why}，不计为独立检验（{cid} 不升到 V3）。"
                  "自己核查自己不算独立；由用户实测、外部原文或另一个 agent 核查时，写明 by")
    rules, notes = claim_alerts(case)
    for f, root, via, e in rules:
        W(f"规则·连带：{f} 经「{EDGE_TYPES[e]}」依赖 {via}；上游 {root} {CLAIM_STATUS[CL[root].get('status')]}。"
          "需重审、收窄或降级后再对外使用")
    for f, to, e, st in notes:
        W(f"提醒·改引用：{f} 「{EDGE_TYPES[e]}」指向{CLAIM_STATUS[st]}的 {to}，更新引用即可，不连带")


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
    dis = case.get("disagreements", [])

    def dcount(r):
        return sum(1 for d in dis if d.get("resolution") == r)

    m = {
        "记录轮数": len(rounds),
        "用户纠正次数": sum(1 for r in rounds if r.get("correction")),
        "分歧数": len(dis),
        "分歧·用户对": dcount("user_right"),
        "分歧·AI 对": dcount("ai_right"),
        "分歧·各对一部分": dcount("both_partly"),
        "分歧·用户决定": dcount("user_decides"),
        "分歧·待检验": dcount("pending"),
        "用户提出的节点": sum(1 for n in case["nodes"] if n.get("proposed_by") == "user" and n.get("kind") != "goal"),
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
    cls = case.get("claims") or []
    if cls:
        m["论断数"] = len(cls)
        for g in range(4):
            m[f"论断·V{g}"] = sum(1 for c in cls if c.get("status", "current") == "current" and claim_grade(case, c) == g)
        m["论断·已撤回或证伪"] = sum(1 for c in cls if c.get("status") in ("withdrawn", "refuted"))
    return m


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
        pr = n.get("park_reference")
        if pr:
            ref = "、".join(pr.get("compared_to", [])) or pr.get("external", "")
            parts.append(f"参照：{pr.get('measure', '')}比 {ref or '?'} 差")
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
        who = "（用户提出）" if n.get("proposed_by") == "user" and n.get("kind") != "goal" else ""
        line = f"{'  ' * depth}{STATUS_MARK.get(n.get('status'), '[?]')} {n['id']} {kind}{n.get('label', '')}{who} —— {tag}"
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
    L += ["", "## 约束", "", "| ID | 约束 | 硬/软 | 依据 | 已确认 | 证据 | 来源 |", "|---|---|---|---|---|---|---|"]
    for c in case["constraints"]:
        src = c.get("source", "")
        if c.get("quote"):
            src += f"：「{c['quote']}」"
        L.append(f"| {c['id']} | {md_cell(c.get('text'))} | {'硬' if c.get('kind') == 'hard' else '软'} | "
                 f"{md_cell(BASIS.get(c.get('basis'), c.get('basis')))} | "
                 f"{'是' if c.get('verified') else '否'} | {md_cell(c.get('evidence'))} | {md_cell(src)} |")
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
    if case.get("disagreements"):
        L += ["## 人机分歧", "", "| ID | 轮次 | 关于 | 类别 | 用户立场 | AI 立场 | 检验 | 结果 | 依据的验证 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for d in case["disagreements"]:
            L.append(f"| {d['id']} | {md_cell(d.get('round'))} | {md_cell(d.get('about'))} | "
                     f"{md_cell(DIS_BASIS.get(d.get('basis'), d.get('basis')))} | {md_cell(d.get('user_position'))} | "
                     f"{md_cell(d.get('ai_position'))} | {md_cell(d.get('test'))} | "
                     f"{md_cell(DIS_RESOLUTION.get(d.get('resolution'), d.get('resolution')))} | {md_cell(d.get('verification'))} |")
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
    if case.get("claims"):
        L += claims_md(case)
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


def claims_md(case):
    edges = claim_edges(case)
    L = ["## 论断", "", "> 等级由验证记录自动计算：V0 未验证，V1 核查通过，V2 可复跑，V3 独立检验；覆盖弱于论断时降一级。", "",
         "| ID | 论断 | 状态 | 等级 | 覆盖 | 上游（边） | 下游（边） |", "|---|---|---|---|---|---|---|"]
    for c in case["claims"]:
        cid = c.get("id")
        cov = c.get("coverage") or {}
        covs = "；".join(x for x in [cov.get("checked", ""), ("未覆盖：" + "、".join(cov.get("not_covered", []))) if cov.get("not_covered") else "",
                                     "弱于论断" if cov.get("weaker_than_claim") else ""] if x)
        up = "、".join(f"{t}（{EDGE_TYPES.get(e, e)}）" for f, t, e in edges if f == cid)
        dn = "、".join(f"{f}（{EDGE_TYPES.get(e, e)}）" for f, t, e in edges if t == cid)
        L.append(f"| {cid} | {md_cell(c.get('statement'))} | {CLAIM_STATUS.get(c.get('status', 'current'), c.get('status'))} | "
                 f"V{claim_grade(case, c)} | {md_cell(covs)} | {md_cell(up)} | {md_cell(dn)} |")
    L.append("")
    return L


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


# ---------------------------------------------------------------- 进展面板（progress.html）

def html_payload(case, errors, warnings):
    jumps = {}
    for k in case["conflicts"]:
        for f in k.get("failed", []):
            jumps[f] = k.get("id")
    return {
        "case": case,
        "labels": {
            "status": STATUS_LABEL, "mark": STATUS_MARK, "kind": KIND_LABEL, "case_status": CASE_STATUS,
            "query": QUERY_TYPES, "basis": BASIS, "dis_basis": DIS_BASIS, "dis_resolution": DIS_RESOLUTION,
            "stage_status": STAGE_STATUS, "stage_mark": STAGE_MARK, "node_order": NODE_STATUS,
        },
        "reasons": {n["id"]: node_reason(n, case) for n in case["nodes"] if n.get("id")},
        "claim_grades": {c["id"]: claim_grade(case, c) for c in (case.get("claims") or []) if c.get("id")},
        "claim_edges": claim_edges(case),
        "claim_status": CLAIM_STATUS, "edge_types": EDGE_TYPES,
        "jumps": jumps,
        "metrics": list(metrics(case).items()),
        "errors": errors,
        "warnings": warnings,
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def render_html(case, errors, warnings):
    import html as _html
    data = json.dumps(html_payload(case, errors, warnings), ensure_ascii=False)
    # 嵌在 <script> 里：转义 < > & 与行分隔符，内容里的任何标签都无法闭合脚本块
    for a, b in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        data = data.replace(a, b)
    title = _html.escape(f"进展面板 · {case.get('title', '')}")
    return HTML_TEMPLATE.replace("__TITLE__", title).replace("__DATA__", data)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="10">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--fg:#1a1a1a;--muted:#4a4a4a;--line:#c8c8c8;--bg:#fafafa;--card:#fff;--focus:#0b57d0}
*{box-sizing:border-box}
body{margin:0;font:14px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;color:var(--fg);background:var(--bg)}
main{max-width:1500px;margin:0 auto;padding:16px 20px 60px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:0 0 8px}h3{font-size:15px;margin:12px 0 6px}
.meta{color:var(--muted);margin:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:12px 0}
.top{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.top .card{margin:0}
.pending{border:2px solid #9a6b00;background:#fffaf0}.running{border:2px solid #1f5fbf;background:#f4f8ff}
.top ul{margin:0;padding-left:20px}.top li{margin:4px 0}
button{font:inherit;color:inherit;cursor:pointer}
button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.link{background:none;border:none;padding:0 2px;color:#0b57d0;text-decoration:underline}
code{font:12px/1.4 ui-monospace,Menlo,monospace;background:#f0f0f0;padding:1px 4px;border-radius:3px;word-break:break-all}
.cols{display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:12px;align-items:start}
.sticky{position:sticky;top:8px;max-height:calc(100vh - 16px);overflow:auto}
#stagewrap{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:12px;align-items:start}
#stagemap{position:relative;overflow:auto}
#stagemap svg{position:absolute;left:0;top:0;pointer-events:none}
.stg{position:absolute;width:200px;height:54px;border-radius:6px;border:2px solid;text-align:left;padding:4px 8px;line-height:1.3;overflow:hidden}
.stg small{display:block;font-size:12px}
.stg[aria-pressed=true]{box-shadow:0 0 0 3px #0b57d0}
.s-done{background:#d7f5dd;border-color:#1b7a34;color:#0b3d18}
.s-partial{background:#fff1c9;border-color:#9a6b00;color:#4a3300}
.s-active{background:#dde9fb;border-color:#1f5fbf;border-width:4px;color:#0d2f66}
.s-todo{background:#f1f1f1;border-color:#6b6b6b;color:#262626}
.s-later{background:#f7f7f7;border-color:#6b6b6b;border-style:dashed;color:#3d3d3d}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--muted);margin:4px 0 8px}
.legend span{display:inline-flex;align-items:center;gap:4px}
.sw{display:inline-block;min-width:26px;text-align:center;border:1px solid;border-radius:3px;padding:0 3px;font:12px ui-monospace,Menlo,monospace}
.controls{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin-bottom:8px}
.controls input[type=search]{padding:4px 8px;border:1px solid #767676;border-radius:4px;min-width:220px}
.tree,.tree ul{list-style:none;margin:0;padding-left:0}
.tree ul{padding-left:22px;border-left:1px dotted #9a9a9a;margin-left:11px}
.row{display:flex;align-items:flex-start;gap:4px;margin:2px 0}
.tog{width:22px;height:22px;flex:none;border:1px solid #767676;background:#fff;border-radius:4px;padding:0;line-height:18px}
.spacer{width:22px;flex:none}
.nb{flex:1;text-align:left;border:1px solid;border-radius:5px;padding:3px 8px;background:#fff}
.nb[aria-pressed=true]{box-shadow:0 0 0 3px #0b57d0}
.nb.ctx{border-style:dashed}
.mark{font:12px ui-monospace,Menlo,monospace;font-weight:700}
.nid{font-weight:700}
.reason{display:block;font-size:12px;color:var(--muted)}
.badge{display:inline-block;font-size:11px;border-radius:9px;padding:0 6px;margin-left:4px;background:#5b2a86;color:#fff;font-weight:600}
.badge.corr{background:#a12a2a}
.n-chosen{background:#d7f5dd;border-color:#1b7a34;color:#0b3d18}
.n-verified{background:#d9f2f2;border-color:#0f6e6e;color:#073b3b}
.n-expanded{background:#dde9fb;border-color:#1f5fbf;color:#0d2f66}
.n-open{background:#f5f5f5;border-color:#6b6b6b;color:#1f1f1f}
.n-parked{background:#fff1c9;border-color:#9a6b00;color:#4a3300}
.n-pruned{background:#fbe0e0;border-color:#a12a2a;color:#5c1010}
.n-failed{background:#f6cccc;border-color:#7a0f0f;color:#4d0808}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}
th{background:#efefef}
details>summary{cursor:pointer;font-weight:600;font-size:16px;padding:2px 0}
dl{margin:0;display:grid;grid-template-columns:max-content 1fr;gap:3px 10px}dt{color:var(--muted)}dd{margin:0}
.panel ul{padding-left:18px;margin:4px 0}
.ok{color:#0b5e24;font-weight:600}.no{color:#8a1c1c;font-weight:600}
.copy{border:1px solid #1f5fbf;background:#1f5fbf;color:#fff;border-radius:4px;padding:3px 10px}
.rounds{list-style:none;padding:0;margin:0}
.rounds>li{border-left:3px solid #1f5fbf;padding:4px 10px;margin:8px 0}
.rounds>li.corr{border-left-color:#a12a2a}
.err{color:#8a1c1c}.warn{color:#6b4a00}
.sr{position:absolute;left:-9999px}
@media (max-width:1000px){.cols,#stagewrap,.top{grid-template-columns:1fr}.sticky{position:static;max-height:none}}
</style>
</head>
<body>
<main id="app">
<noscript><p>这个面板需要启用 JavaScript；真源是同目录的 case.json，也可以看 tree.md。</p></noscript>
</main>
<svg id="svg-proto" style="display:none" aria-hidden="true" focusable="false"><defs><marker id="arrowhead" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#555"/></marker></defs></svg>
<script type="application/json" id="case-data">__DATA__</script>
<script>
(function () {
  'use strict';
  var D = JSON.parse(document.getElementById('case-data').textContent);
  var C = D.case, L = D.labels;
  var KEY = 'pas-progress:' + (C.id || '');
  var state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { state = {}; }
  state.collapsed = state.collapsed || {};
  state.open = state.open || {};
  state.roundsOpen = state.roundsOpen || {};
  state.who = state.who || 'all';
  state.q = state.q || '';
  function save() {
    state.scroll = window.scrollY;
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  }

  // 只用 textContent / setAttribute 写入内容：案例文本永远不会被当成 HTML 解析
  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === 'text') e.textContent = String(v);
      else if (k === 'class') e.className = v;
      else if (k.slice(0, 2) === 'on') e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : String(v));
    });
    (kids || []).forEach(function (c) {
      if (c === null || c === undefined || c === false) return;
      e.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
    });
    return e;
  }
  function arr(x) { return Array.isArray(x) ? x : (x === null || x === undefined || x === '' ? [] : [x]); }
  function byId(list) { var m = {}; arr(list).forEach(function (x) { if (x && x.id) m[x.id] = x; }); return m; }
  function txt(x) { return Array.isArray(x) ? x.join('；') : (x === null || x === undefined || x === '' ? '—' : String(x)); }

  var nodes = arr(C.nodes), N = byId(nodes), CI = byId(C.constraints), EV = byId(C.evidence);
  var stages = arr(C.stages), SI = byId(stages);
  var kids = {};
  nodes.forEach(function (n) { var p = n.parent || ''; (kids[p] = kids[p] || []).push(n); });
  var rounds = arr(C.rounds);
  var latest = rounds.reduce(function (m, r) { return typeof r.n === 'number' && r.n > m ? r.n : m; }, 0);
  function changedLatest(n) {
    if (!latest) return false;
    if (n.round === latest) return true;
    return arr(n.history).some(function (h) { return h.round === latest; });
  }
  function stLabel(s) { return L.status[s] || s || '?'; }
  function mark(s) { return L.mark[s] || '[?]'; }

  var app = document.getElementById('app');
  var live = el('p', { class: 'sr', 'aria-live': 'polite', id: 'live' });

  // ------------------------------------------------ 引用按钮：跳到节点或阶段
  function refButton(id) {
    if (N[id]) return el('button', { class: 'link', type: 'button', text: id, title: N[id].label || '', onclick: function () { selectNode(id, true); } });
    if (SI[id]) return el('button', { class: 'link', type: 'button', text: id, title: SI[id].label || '', onclick: function () { selectStage(id, true); } });
    if (CI[id]) return el('span', { text: id, title: CI[id].text || '' });
    return el('span', { text: id });
  }
  function refList(ids) {
    var out = el('span');
    arr(ids).forEach(function (id, i) { if (i) out.appendChild(document.createTextNode('、')); out.appendChild(refButton(id)); });
    return out;
  }

  // ------------------------------------------------ 头部
  function header() {
    var p = C.problem || {};
    return el('header', null, [
      el('h1', { text: C.title || C.id }),
      el('p', { class: 'meta' }, [
        '案例 ', el('code', { text: C.id || '' }),
        ' · 状态：' + (L.case_status[C.status] || C.status || '—'),
        ' · ' + (L.query[p.query_type] || p.query_type || ''),
        ' · 最后更新：' + (C.updated || '—'),
        ' · 共 ' + rounds.length + ' 轮（最新第 ' + (latest || '—') + ' 轮）',
        ' · 生成于 ' + D.generated + '，每 10 秒自动刷新'
      ]),
      p.goal ? el('p', { class: 'meta' }, ['目标：' + p.goal]) : null
    ]);
  }
  function topBoxes() {
    var pend = arr(C.pending), run = arr(C.running);
    var pl = el('ul');
    pend.forEach(function (x) {
      var about = arr(x.about);
      pl.appendChild(el('li', null, [
        el('strong', { text: (x.id || '') + ' ' }), x.question || '',
        about.length ? el('span', { class: 'meta' }, ['（关于 ', refList(about), '）']) : null,
        x.since_round ? el('span', { class: 'meta', text: ' 自第 ' + x.since_round + ' 轮' }) : null
      ]));
    });
    if (!pend.length) pl.appendChild(el('li', { text: '暂无' }));
    var rl = el('ul');
    run.forEach(function (x) {
      rl.appendChild(el('li', null, [
        el('strong', { text: x.label || '' }),
        x.report_path ? el('span', null, [' → ', el('code', { text: x.report_path })]) : null,
        x.started ? el('span', { class: 'meta', text: ' （开始于 ' + x.started + '）' }) : null
      ]));
    });
    if (!run.length) rl.appendChild(el('li', { text: '暂无' }));
    return el('div', { class: 'top' }, [
      el('section', { class: 'card pending', 'aria-labelledby': 'h-pend' }, [el('h2', { id: 'h-pend', text: '等你决定（' + pend.length + '）' }), pl]),
      el('section', { class: 'card running', 'aria-labelledby': 'h-run' }, [el('h2', { id: 'h-run', text: '正在后台运行（' + run.length + '）' }), rl])
    ]);
  }

  // ------------------------------------------------ 阶段图
  var BW = 200, BH = 54, GX = 24, GY = 36, PAD = 10;
  function stageSection() {
    var sec = el('section', { class: 'card', 'aria-labelledby': 'h-stage' }, [el('h2', { id: 'h-stage', text: '阶段图' })]);
    if (!stages.length) { sec.appendChild(el('p', { class: 'meta', text: 'case.json 里还没有 stages。' })); return sec; }
    var lg = el('div', { class: 'legend' });
    Object.keys(L.stage_status).forEach(function (k) {
      lg.appendChild(el('span', null, [el('span', { class: 'sw s-' + k, text: L.stage_mark[k] }), L.stage_status[k]]));
    });
    lg.appendChild(el('span', { text: '箭头：依赖 → 后续阶段；点击阶段看产出与缺口' }));
    sec.appendChild(lg);
    // 分层：层号 = 依赖链最长长度
    var layer = {}, busy = {};
    function lay(id) {
      if (layer[id] !== undefined) return layer[id];
      if (busy[id]) return 0;
      busy[id] = true;
      var deps = arr(SI[id] && SI[id].depends_on).filter(function (d) { return SI[d]; });
      var v = deps.length ? 1 + Math.max.apply(null, deps.map(lay)) : 0;
      busy[id] = false;
      layer[id] = v;
      return v;
    }
    stages.forEach(function (s) { if (s.id) lay(s.id); });
    // 没有依赖的阶段放到最早的后续阶段上一层，箭头就不会穿过无关的阶段
    stages.forEach(function (s) {
      if (!s.id || arr(s.depends_on).some(function (d) { return SI[d]; })) return;
      var next = stages.filter(function (t) { return arr(t.depends_on).indexOf(s.id) >= 0; }).map(function (t) { return layer[t.id]; });
      if (next.length) layer[s.id] = Math.max(0, Math.min.apply(null, next) - 1);
    });
    var rows = [];
    stages.forEach(function (s) { if (!s.id) return; var l = layer[s.id]; (rows[l] = rows[l] || []).push(s); });
    rows = rows.map(function (r) { return r || []; });
    var maxw = Math.max.apply(null, rows.map(function (r) { return r.length; }));
    var W = PAD * 2 + maxw * BW + (maxw - 1) * GX, H = PAD * 2 + rows.length * BH + (rows.length - 1) * GY;
    var pos = {};
    rows.forEach(function (r, li) {
      var rw = r.length * BW + (r.length - 1) * GX, x0 = (W - rw) / 2;
      r.forEach(function (s, i) { pos[s.id] = { x: x0 + i * (BW + GX), y: PAD + li * (BH + GY), l: li }; });
    });
    var map = el('div', { id: 'stagemap', role: 'group', 'aria-label': '阶段依赖图' });
    map.style.height = (H + 4) + 'px';
    var inner = el('div');
    inner.style.position = 'relative'; inner.style.width = W + 'px'; inner.style.height = H + 'px';
    // 直接搬用页面里的空 SVG（含箭头 marker），避免在脚本里写命名空间地址
    var svg = document.getElementById('svg-proto');
    svg.parentNode.removeChild(svg);
    svg.removeAttribute('id'); svg.style.display = '';
    svg.setAttribute('width', W); svg.setAttribute('height', H);
    var NS = svg.namespaceURI;
    stages.forEach(function (s) {
      arr(s.depends_on).forEach(function (d) {
        var a = pos[d], b = pos[s.id];
        if (!a || !b) return;
        var x1 = a.x + BW / 2, y1 = a.y + BH, x2 = b.x + BW / 2, y2 = b.y - 2, dpath;
        if (b.l - a.l > 1 && Math.abs(x1 - x2) < 1) {
          var bx = Math.max(x1, x2) + BW / 2 + 30;
          dpath = 'M' + (a.x + BW) + ' ' + (a.y + BH / 2) + ' C' + bx + ' ' + (a.y + BH / 2) + ' ' + bx + ' ' + (b.y + BH / 2) + ' ' + (b.x + BW + 2) + ' ' + (b.y + BH / 2);
        } else {
          var my = (y1 + y2) / 2;
          dpath = 'M' + x1 + ' ' + y1 + ' C' + x1 + ' ' + my + ' ' + x2 + ' ' + my + ' ' + x2 + ' ' + y2;
        }
        var p = document.createElementNS(NS, 'path');
        p.setAttribute('d', dpath); p.setAttribute('fill', 'none'); p.setAttribute('stroke', '#555');
        p.setAttribute('stroke-width', '1.6'); p.setAttribute('marker-end', 'url(#arrowhead)');
        svg.appendChild(p);
      });
    });
    inner.appendChild(svg);
    stages.forEach(function (s) {
      var q = pos[s.id];
      if (!q) return;
      var st = L.stage_status[s.status] ? s.status : 'todo';
      var b = el('button', {
        type: 'button', class: 'stg s-' + st, 'data-stage': s.id, 'aria-pressed': state.stage === s.id ? 'true' : 'false',
        'aria-label': s.id + ' ' + (s.label || '') + '，' + (L.stage_status[s.status] || s.status),
        onclick: function () { selectStage(s.id); }
      }, [
        el('span', { text: (L.stage_mark[s.status] || '?') + ' ' + s.id + ' ' + (s.label || '') }),
        el('small', { text: L.stage_status[s.status] || ('未知状态 ' + s.status) })
      ]);
      b.style.left = q.x + 'px'; b.style.top = q.y + 'px';
      inner.appendChild(b);
    });
    map.appendChild(inner);
    sec.appendChild(el('div', { id: 'stagewrap' }, [map, el('div', { id: 'stagedetail', class: 'panel', 'aria-live': 'polite' })]));
    return sec;
  }
  function renderStageDetail() {
    var box = document.getElementById('stagedetail');
    if (!box) return;
    box.textContent = '';
    var s = SI[state.stage];
    if (!s) { box.appendChild(el('p', { class: 'meta', text: '点击左侧的阶段查看已有产出和还差什么。' })); return; }
    box.appendChild(el('h3', { text: s.id + ' ' + (s.label || '') }));
    var outs = el('ul');
    arr(s.outputs).forEach(function (o) { outs.appendChild(el('li', null, [/[\/\\]|\.md$|\.json$/.test(o) ? el('code', { text: o }) : o])); });
    if (!arr(s.outputs).length) outs.appendChild(el('li', { text: '—' }));
    var pend = arr(C.pending).filter(function (p) { return arr(p.about).indexOf(s.id) >= 0; });
    box.appendChild(el('dl', null, [
      el('dt', { text: '状态' }), el('dd', { text: (L.stage_mark[s.status] || '') + ' ' + (L.stage_status[s.status] || s.status) }),
      el('dt', { text: '依赖' }), el('dd', null, [arr(s.depends_on).length ? refList(s.depends_on) : '—']),
      el('dt', { text: '已有产出' }), el('dd', null, [outs]),
      el('dt', { text: '还差什么' }), el('dd', { text: s.missing || '—' }),
      el('dt', { text: '相关节点' }), el('dd', null, [arr(s.nodes).length ? refList(s.nodes) : '—']),
      pend.length ? el('dt', { text: '等你决定' }) : null,
      pend.length ? el('dd', { text: pend.map(function (p) { return p.id + ' ' + p.question; }).join('；') }) : null
    ]));
  }
  function selectStage(id, scroll) {
    state.stage = id; save();
    document.querySelectorAll('.stg').forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-stage') === id ? 'true' : 'false'); });
    renderStageDetail();
    var b = document.querySelector('.stg[data-stage="' + CSS.escape(id) + '"]');
    if (scroll && b) { b.scrollIntoView({ block: 'center' }); b.focus(); }
  }

  // ------------------------------------------------ 解空间树
  function treeSection() {
    var sec = el('section', { class: 'card', 'aria-labelledby': 'h-tree' }, [el('h2', { id: 'h-tree', text: '解空间' })]);
    var lg = el('div', { class: 'legend' });
    L.node_order.forEach(function (s) { lg.appendChild(el('span', null, [el('span', { class: 'sw n-' + s, text: mark(s) }), stLabel(s)])); });
    lg.appendChild(el('span', null, [el('span', { class: 'badge', text: '本轮' }), '第 ' + (latest || '—') + ' 轮新增或改动']));
    sec.appendChild(lg);
    sec.appendChild(el('p', { class: 'meta', text: '[~] 搁置（软偏好或依据未核实，可重审）　[x] 淘汰（违反已确认的硬约束）　[!] 失败（现实尝试或验证失败）' }));
    var hide = el('input', { type: 'checkbox', id: 'f-hide' });
    hide.checked = !!state.hide;
    hide.addEventListener('change', function () { state.hide = hide.checked; save(); renderTree(); });
    var who = el('select', { id: 'f-who' }, [
      el('option', { value: 'all', text: '全部' }), el('option', { value: 'user', text: '用户提出' }), el('option', { value: 'ai', text: 'AI 提出' })
    ]);
    who.value = state.who;
    who.addEventListener('change', function () { state.who = who.value; save(); renderTree(); });
    var q = el('input', { type: 'search', id: 'f-q', placeholder: '搜索 ID、内容、备注' });
    q.value = state.q;
    q.addEventListener('input', function () { state.q = q.value; save(); renderTree(); });
    q.addEventListener('focus', function () { state.qFocus = true; save(); });
    q.addEventListener('blur', function () { state.qFocus = false; save(); });
    var bExp = el('button', { type: 'button', text: '全部展开', onclick: function () { state.collapsed = {}; save(); renderTree(); } });
    var bCol = el('button', { type: 'button', text: '全部折叠', onclick: function () {
      state.collapsed = {}; nodes.forEach(function (n) { if (kids[n.id] && n.parent) state.collapsed[n.id] = true; }); save(); renderTree();
    } });
    sec.appendChild(el('div', { class: 'controls' }, [
      el('label', null, [hide, ' 隐藏淘汰与失败']),
      el('label', null, ['提出者 ', who]),
      el('label', null, ['搜索 ', q]),
      bExp, bCol, el('span', { id: 'tree-count', class: 'meta' })
    ]));
    sec.appendChild(el('ul', { class: 'tree', id: 'tree', 'aria-label': '解空间树' }));
    return sec;
  }
  function outOf(n) {
    for (var cur = n, i = 0; cur && i <= nodes.length; cur = N[cur.parent], i++) if (cur.status === 'pruned' || cur.status === 'failed') return true;
    return false;
  }
  function renderTree() {
    var ul = document.getElementById('tree');
    if (!ul) return;
    var active = document.activeElement, focusId = active && active.getAttribute && active.getAttribute('data-focus');
    ul.textContent = '';
    var q = (state.q || '').trim().toLowerCase(), filtering = !!q || state.who !== 'all';
    var match = {}, show = {}, nm = 0;
    nodes.forEach(function (n) {
      if (state.hide && outOf(n)) return;
      var ok = (state.who === 'all' || n.proposed_by === state.who) &&
        (!q || [n.id, n.label, n.note, D.reasons[n.id]].join(' ').toLowerCase().indexOf(q) >= 0);
      if (!ok) return;
      match[n.id] = true; nm++;
      for (var cur = n, i = 0; cur && i <= nodes.length; cur = N[cur.parent], i++) show[cur.id] = true;
    });
    function item(n, depth) {
      var cs = (kids[n.id] || []).filter(function (c) { return show[c.id]; });
      var collapsed = !filtering && !!state.collapsed[n.id];
      var row = el('div', { class: 'row' });
      if (cs.length) {
        row.appendChild(el('button', {
          type: 'button', class: 'tog', 'aria-expanded': collapsed ? 'false' : 'true', 'data-focus': 't-' + n.id,
          'aria-label': (collapsed ? '展开 ' : '折叠 ') + n.id + '（' + cs.length + ' 个子节点）', text: collapsed ? '▸' : '▾',
          onclick: function () { state.collapsed[n.id] = !collapsed; save(); renderTree(); }
        }));
      } else row.appendChild(el('span', { class: 'spacer', 'aria-hidden': 'true' }));
      var kind = (n.kind === 'candidate' || n.kind === 'goal') ? '' : '〔' + (L.kind[n.kind] || n.kind || '') + '〕';
      var who = n.proposed_by === 'user' && n.kind !== 'goal' ? '（用户提出）' : '';
      var reason = D.reasons[n.id] || '';
      var jump = D.jumps[n.id];
      var btn = el('button', {
        type: 'button', class: 'nb n-' + (n.status || 'open') + (filtering && !match[n.id] ? ' ctx' : ''), 'data-focus': 'n-' + n.id,
        'aria-pressed': state.sel === n.id ? 'true' : 'false', onclick: function () { selectNode(n.id); }
      }, [
        el('span', { class: 'mark', text: mark(n.status) }), ' ', el('span', { class: 'nid', text: n.id }), ' ',
        kind, n.label || '', who, ' —— ' + stLabel(n.status),
        changedLatest(n) ? el('span', { class: 'badge', text: '本轮' }) : null,
        filtering && !match[n.id] ? el('span', { class: 'meta', text: '（上层，未匹配）' }) : null,
        reason || jump ? el('span', { class: 'reason', text: (reason ? '理由：' + reason : '') + (jump ? '  ⟶ 冲突核 ' + jump : '') }) : null
      ]);
      row.appendChild(btn);
      var li = el('li', null, [row]);
      if (cs.length && !collapsed) {
        var sub = el('ul', { 'aria-label': n.id + ' 的子节点' });
        cs.forEach(function (c) { sub.appendChild(item(c, depth + 1)); });
        li.appendChild(sub);
      }
      return li;
    }
    (kids[''] || []).forEach(function (r) { if (show[r.id]) ul.appendChild(item(r, 0)); });
    document.getElementById('tree-count').textContent = filtering ? ('匹配 ' + nm + ' 个节点') : ('共 ' + nodes.length + ' 个节点');
    if (focusId) { var f = ul.querySelector('[data-focus="' + CSS.escape(focusId) + '"]'); if (f) f.focus(); }
  }

  // ------------------------------------------------ 节点详情
  function cLine(id) {
    var c = CI[id];
    if (!c) return el('li', { text: id + '（不存在）' });
    return el('li', null, [el('strong', { text: id }), ' ' + (c.kind === 'hard' ? '硬' : '软') + ' · ' + (L.basis[c.basis] || c.basis || '依据未标') + ' · ',
      el('span', { class: c.verified ? 'ok' : 'no', text: c.verified ? '已确认' : '未确认' }), '：' + (c.text || '')]);
  }
  function evLine(id) {
    var e = EV[id];
    if (!e) return el('li', { text: id + '（不存在）' });
    return el('li', null, [el('strong', { text: id }), ' ', el('span', { class: e.verified ? 'ok' : 'no', text: e.verified ? '✓ 已核实' : '✗ 未核实' }),
      ' （' + (e.type || '') + '）' + (e.claim || ''), e.source ? el('span', { class: 'meta', text: ' —— 来源：' + e.source }) : null]);
  }
  function copyText(text, status) {
    function done(ok) { status.textContent = ok ? '已复制：' + text : '复制失败，请手动复制：' + text; }
    function fallback() {
      var ta = el('textarea', { readonly: true, 'aria-hidden': 'true' });
      ta.value = text; ta.style.position = 'fixed'; ta.style.left = '-9999px';
      document.body.appendChild(ta); ta.select();
      var ok = false; try { ok = document.execCommand('copy'); } catch (e) {}
      document.body.removeChild(ta); return ok;
    }
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(fallback()); });
    else done(fallback());
  }
  function renderDetail() {
    var box = document.getElementById('detail');
    box.textContent = '';
    box.appendChild(el('h2', { id: 'h-detail', text: '节点详情' }));
    var n = N[state.sel];
    if (!n) { box.appendChild(el('p', { class: 'meta', text: '点击解空间里的节点查看详情；"复制引用"后可以直接粘贴到对话里。' })); return; }
    var ref = n.id + '：' + (n.label || '');
    var status = el('span', { class: 'meta', role: 'status' });
    box.appendChild(el('h3', { text: n.id + ' ' + (n.label || '') }));
    box.appendChild(el('p', null, [el('button', { type: 'button', class: 'copy', text: '复制引用', onclick: function () { copyText(ref, status); } }), ' ', status]));
    var vs = arr(C.verifications).filter(function (v) { return v.target === n.id; });
    var ds = arr(C.disagreements).filter(function (d) { return d.about === n.id || arr(n.pruned_by).concat(arr(n.parked_by)).indexOf(d.about) >= 0; });
    var ks = arr(C.conflicts).filter(function (k) { return arr(k.failed).indexOf(n.id) >= 0 || k.jump_to === n.id; });
    var ls = arr(C.links).filter(function (l) { return l.from === n.id || l.to === n.id; });
    var ss = stages.filter(function (s) { return arr(s.nodes).indexOf(n.id) >= 0; });
    var dl = el('dl', null, [
      el('dt', { text: '类型' }), el('dd', { text: L.kind[n.kind] || n.kind || '—' }),
      el('dt', { text: '状态' }), el('dd', { text: mark(n.status) + ' ' + stLabel(n.status) + (changedLatest(n) ? '（本轮有变化）' : '') }),
      el('dt', { text: '提出者' }), el('dd', { text: n.proposed_by === 'user' ? '用户' : n.proposed_by === 'ai' ? 'AI' : '—' }),
      el('dt', { text: '首次出现' }), el('dd', { text: n.round ? '第 ' + n.round + ' 轮' : '—' }),
      el('dt', { text: '父节点' }), el('dd', null, [n.parent ? refButton(n.parent) : '—（根）']),
      el('dt', { text: '子节点' }), el('dd', null, [(kids[n.id] || []).length ? refList((kids[n.id] || []).map(function (c) { return c.id; })) : '—']),
      ss.length ? el('dt', { text: '所属阶段' }) : null, ss.length ? el('dd', null, [refList(ss.map(function (s) { return s.id; }))]) : null,
      el('dt', { text: '备注' }), el('dd', { text: n.note || '—' }),
      el('dt', { text: '理由' }), el('dd', { text: D.reasons[n.id] || '—' })
    ]);
    box.appendChild(dl);
    function block(title, items) {
      if (!items.length) return;
      box.appendChild(el('h3', { text: title }));
      box.appendChild(el('ul', null, items));
    }
    block('淘汰依据（pruned_by）', arr(n.pruned_by).map(cLine));
    block('搁置依据（parked_by）', arr(n.parked_by).map(cLine));
    var pr = n.park_reference;
    if (pr) block('搁置时的比较（park_reference）', [el('li', null, ['维度 ' + (pr.measure || '—') + '（' + (pr.direction === 'higher' ? '越高越好' : '越低越好') + '）；参照 ',
      arr(pr.compared_to).length ? refList(pr.compared_to) : '—', pr.external ? '；台账外：' + pr.external : '', pr.note ? '；' + pr.note : ''])]);
    block('证据', arr(n.evidence).map(evLine));
    block('原问题里的验证', vs.map(function (v) {
      return el('li', null, [el('strong', { text: v.id }), ' ', el('span', { class: v.result === 'pass' ? 'ok' : v.result === 'fail' ? 'no' : '', text: v.result || '' }),
        ' ' + (v.method || '') + (v.date ? '（' + v.date + '）' : '') + (v.note ? '：' + v.note : ''), arr(v.evidence).length ? el('ul', null, arr(v.evidence).map(evLine)) : null]);
    }));
    block('相关分歧', ds.map(function (d) {
      return el('li', null, [el('strong', { text: d.id }), ' 第 ' + (d.round || '?') + ' 轮 · ' + (L.dis_basis[d.basis] || d.basis || '') + ' · 结果：' + (L.dis_resolution[d.resolution] || d.resolution || ''),
        el('ul', null, [el('li', { text: '用户：' + (d.user_position || '—') }), el('li', { text: 'AI：' + (d.ai_position || '—') }),
          el('li', { text: '检验：' + (d.test || '—') + (d.verification ? '（' + d.verification + '）' : '') }), d.note ? el('li', { text: '备注：' + d.note }) : null])]);
    }));
    block('冲突核', ks.map(function (k) {
      return el('li', null, [el('strong', { text: k.id }), ' 共同原因「' + (k.common_cause || '') + '」；一起失败：', refList(k.failed), '；跳到 ', k.jump_to ? refButton(k.jump_to) : '—']);
    }));
    block('其他关系', ls.map(function (l) {
      return el('li', null, [refButton(l.from), ' —' + (l.type || '') + '→ ', refButton(l.to), l.note ? '：' + l.note : '']);
    }));
    var hs = arr(n.history);
    box.appendChild(el('h3', { text: '历史（' + hs.length + '）' }));
    if (hs.length) {
      box.appendChild(el('table', null, [el('thead', null, [el('tr', null, [el('th', { scope: 'col', text: '轮' }), el('th', { scope: 'col', text: '状态' }), el('th', { scope: 'col', text: '说明' })])]),
        el('tbody', null, hs.map(function (h) { return el('tr', null, [el('td', { text: h.round === undefined ? '—' : h.round }), el('td', { text: mark(h.status) + ' ' + stLabel(h.status) }), el('td', { text: h.note || '—' })]); }))]));
    } else box.appendChild(el('p', { class: 'meta', text: '无记录' }));
  }
  function selectNode(id, scroll) {
    state.sel = id;
    if (scroll) {  // 展开祖先，保证节点可见
      for (var cur = N[N[id] && N[id].parent], i = 0; cur && i <= nodes.length; cur = N[cur.parent], i++) delete state.collapsed[cur.id];
    }
    save(); renderTree(); renderDetail();
    var b = document.querySelector('[data-focus="n-' + CSS.escape(id) + '"]');
    if (scroll && b) { b.scrollIntoView({ block: 'center' }); b.focus(); }
    else if (window.matchMedia('(max-width:1000px)').matches) document.getElementById('detail').scrollIntoView();
  }

  // ------------------------------------------------ 表格
  function table(headers, rows) {
    return el('div', { style: 'overflow:auto' }, [el('table', null, [
      el('thead', null, [el('tr', null, headers.map(function (h) { return el('th', { scope: 'col', text: h }); }))]),
      el('tbody', null, rows.map(function (r) { return el('tr', null, r.map(function (c) { return el('td', null, [c instanceof Node ? c : txt(c)]); })); }))
    ])]);
  }
  function det(id, title, body, openDefault) {
    var d = el('details', { class: 'card', id: id }, [el('summary', null, [el('h2', { text: title, style: 'display:inline;font-size:16px' })]), body]);
    d.open = state.open[id] === undefined ? !!openDefault : !!state.open[id];
    d.addEventListener('toggle', function () { state.open[id] = d.open; save(); });
    return d;
  }
  function yes(v, a, b) { return el('span', { class: v ? 'ok' : 'no', text: v ? a : b }); }
  function tables() {
    var cs = arr(C.constraints), ds = arr(C.disagreements), es = arr(C.evidence);
    return [
      det('t-cons', '约束（' + cs.length + '）', table(['ID', '约束', '硬/软', '依据', '已确认', '证据', '来源'], cs.map(function (c) {
        return [c.id, c.text, c.kind === 'hard' ? '硬' : '软', L.basis[c.basis] || c.basis, yes(c.verified, '是', '否'), c.evidence, (c.source || '') + (c.quote ? '：「' + c.quote + '」' : '')];
      })), false),
      det('t-dis', '人机分歧（' + ds.length + '）', table(['ID', '轮次', '关于', '类别', '用户立场', 'AI 立场', '检验', '结果', '依据的验证', '备注'], ds.map(function (d) {
        return [d.id, d.round, d.about ? refButton(d.about) : '—', L.dis_basis[d.basis] || d.basis, d.user_position, d.ai_position, d.test, L.dis_resolution[d.resolution] || d.resolution, d.verification, d.note];
      })), false),
      det('t-ev', '证据（' + es.length + '）', table(['ID', '断言', '类型', '已核实', '来源', '日期'], es.map(function (e) {
        return [e.id, e.claim, e.type, yes(e.verified, '✓ 是', '✗ 否'), e.source, e.date];
      })), false)
    ];
  }

  // ------------------------------------------------ 论断台账
  function claimsSection() {
    var cls = arr(C.claims); if (!cls.length) return null;
    var CLI = byId(cls), G = D.claim_grades || {}, ED = D.claim_edges || [];
    var alerts = D.warnings.filter(function (w) { return /^规则·连带|^提醒·改引用/.test(w); });
    var box = el('div');
    if (alerts.length) box.appendChild(el('ul', null, alerts.map(function (w) { return el('li', { class: w.indexOf('规则') === 0 ? 'err' : 'warn', text: w }); })));
    var info = el('div', { class: 'card', style: 'margin-top:8px' }, [el('p', { class: 'meta', text: '点论断 ID 看详情。等级由验证记录自动计算：V0 未验证、V1 核查通过、V2 可复跑、V3 独立检验；覆盖弱于论断时降一级。' })]);
    function showClaim(id) {
      var c = CLI[id]; info.textContent = ''; state.claimSel = id; save();
      var cov = c.coverage || {};
      var vs = arr(C.verifications).filter(function (v) { return v.target === id; });
      var up = ED.filter(function (e) { return e[0] === id; }), dn = ED.filter(function (e) { return e[1] === id; });
      function cl(eid) { return el('button', { class: 'link', type: 'button', text: eid, onclick: function () { showClaim(eid); } }); }
      [el('h3', { text: id + '：' + (c.statement || '') }),
       el('p', { text: '状态：' + (D.claim_status[c.status || 'current'] || c.status) + ' · 等级 V' + G[id] + (c.supersedes ? ' · 取代 ' + c.supersedes : '') }),
       el('p', null, ['关于：', c.about ? refList(c.about) : '—']),
       el('p', { text: '证据：' + txt(c.evidence) }),
       el('p', { text: '已核对：' + (cov.checked || '—') }),
       el('p', { text: '未覆盖：' + txt(cov.not_covered) + (cov.weaker_than_claim ? '（弱于论断，等级已降一级）' : '') }),
       el('p', null, ['上游：'].concat(up.length ? up.map(function (e) { return el('span', null, [cl(e[1]), '（' + D.edge_types[e[2]] + '） ']); }) : ['—'])),
       el('p', null, ['下游：'].concat(dn.length ? dn.map(function (e) { return el('span', null, [cl(e[0]), '（' + D.edge_types[e[2]] + '） ']); }) : ['—'])),
       el('p', { text: '验证：' + (vs.length ? vs.map(function (v) { return v.id + ' ' + v.result + (v.independent ? ((v.by && String(v.by).trim().toLowerCase() !== String(c.proposed_by || 'ai').trim().toLowerCase()) ? '·独立（' + v.by + '）' : '·独立（不认：未写检验者或检验者即提出者）') : '') + (v.rerun ? '·可复跑' : '') + '：' + (v.method || ''); }).join('；') : '—') }),
       c.withdrawal ? el('p', { class: 'err', text: '撤回：' + (c.withdrawal.date || '') + ' ' + (c.withdrawal.scope === 'proof' ? '（理由失效，陈述未判定）' : '（陈述作废）') + ' 根因：' + (c.withdrawal.root_cause || '—') }) : null,
       arr(c.history).length ? el('ul', null, arr(c.history).map(function (h) { return el('li', { text: (h.round || h.date || '') + ' ' + h.kind + '：' + (h.note || '') }); })) : null
      ].forEach(function (x) { if (x) info.appendChild(x); });
    }
    box.appendChild(table(['ID', '论断', '状态', '等级', '上游', '下游'], cls.map(function (c) {
      return [el('button', { class: 'link', type: 'button', text: c.id, onclick: function () { showClaim(c.id); } }), c.statement,
        D.claim_status[c.status || 'current'] || c.status, el('span', { class: 'badge', text: 'V' + G[c.id] }),
        ED.filter(function (e) { return e[0] === c.id; }).map(function (e) { return e[1] + '·' + D.edge_types[e[2]]; }).join('、') || '—',
        ED.filter(function (e) { return e[1] === c.id; }).map(function (e) { return e[0] + '·' + D.edge_types[e[2]]; }).join('、') || '—'];
    })));
    box.appendChild(info);
    if (state.claimSel && CLI[state.claimSel]) showClaim(state.claimSel);
    return det('t-claims', '论断台账（' + cls.length + '）', box, true);
  }
  // ------------------------------------------------ 探索过程
  function roundsSection() {
    var ol = el('ol', { class: 'rounds', reversed: true });
    rounds.slice().reverse().forEach(function (r) {
      var key = String(r.n), full = r.user || '', LIM = 80, long = full.length > LIM, open = !!state.roundsOpen[key];
      var words = el('span', { text: long && !open ? full.slice(0, LIM) + '…' : full });
      var tog = long ? el('button', { type: 'button', class: 'link', 'aria-expanded': open ? 'true' : 'false', text: open ? '收起' : '展开',
        onclick: function () {
          open = !open; state.roundsOpen[key] = open; save();
          words.textContent = open ? full : full.slice(0, LIM) + '…';
          tog.textContent = open ? '收起' : '展开'; tog.setAttribute('aria-expanded', open ? 'true' : 'false');
        } }) : null;
      var a = r.real_world_attempt;
      ol.appendChild(el('li', { class: r.correction ? 'corr' : '' }, [
        el('h3', null, ['第 ' + r.n + ' 轮', r.date ? el('span', { class: 'meta', text: ' · ' + r.date }) : null,
          r.correction ? el('span', { class: 'badge corr', text: '用户纠正' }) : null, r.n === latest ? el('span', { class: 'badge', text: '最新' }) : null]),
        el('p', { style: 'margin:2px 0' }, ['用户：', words, tog ? ' ' : null, tog]),
        arr(r.actions).length ? el('ul', null, arr(r.actions).map(function (x) { return el('li', { text: x }); })) : null,
        arr(r.questions).length ? el('p', { class: 'meta', style: 'margin:2px 0', text: '问用户：' + arr(r.questions).join('；') }) : null,
        a ? el('p', { style: 'margin:2px 0', text: '现实尝试：' + (a.target || '') + ' → ' + (a.result || '') + (a.note ? '（' + a.note + '）' : '') }) : null
      ]));
    });
    return det('t-rounds', '探索过程（' + rounds.length + ' 轮，最新在上）', ol, true);
  }

  function metricsSection() {
    return det('t-metrics', '指标', table(['指标', '值'], D.metrics.map(function (kv) { return [kv[0], kv[1] === null ? '—' : String(kv[1])]; })), true);
  }
  function validationSection() {
    var ul = el('ul');
    D.errors.forEach(function (e) { ul.appendChild(el('li', { class: 'err', text: '错误：' + e })); });
    D.warnings.forEach(function (w) { ul.appendChild(el('li', { class: 'warn', text: '提醒：' + w })); });
    if (!D.errors.length && !D.warnings.length) ul.appendChild(el('li', { class: 'ok', text: '全部通过。' }));
    return det('t-check', '校验：错误 ' + D.errors.length + ' 条，提醒 ' + D.warnings.length + ' 条', ul, D.errors.length > 0);
  }

  // ------------------------------------------------ 组装
  app.appendChild(header());
  app.appendChild(live);
  app.appendChild(topBoxes());
  app.appendChild(stageSection());
  app.appendChild(el('div', { class: 'cols' }, [treeSection(), el('aside', { id: 'detail', class: 'card sticky panel', 'aria-labelledby': 'h-detail' })]));
  var cs_ = claimsSection(); if (cs_) app.appendChild(cs_);
  tables().forEach(function (t) { app.appendChild(t); });
  app.appendChild(roundsSection());
  app.appendChild(metricsSection());
  app.appendChild(validationSection());
  renderTree(); renderDetail(); renderStageDetail();
  if (state.qFocus) { var qi = document.getElementById('f-q'); qi.focus(); qi.setSelectionRange(qi.value.length, qi.value.length); }
  window.scrollTo(0, state.scroll || 0);
  var t = null;
  window.addEventListener('scroll', function () { clearTimeout(t); t = setTimeout(save, 150); });
  window.addEventListener('pagehide', save);
  window.addEventListener('beforeunload', save);
})();
</script>
</body>
</html>
"""


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
    (f.parent / "progress.html").write_text(render_html(case, errors, warnings), encoding="utf-8")
    print(f"已写入：{f.parent / 'tree.md'}，{f.parent / 'graph.canvas'}，{f.parent / 'progress.html'}")
    sys.exit(1 if errors else 0)


def cmd_html(args):
    f, case = load_case(args.case)
    errors, warnings = check(case)
    (f.parent / "progress.html").write_text(render_html(case, errors, warnings), encoding="utf-8")
    for e in errors:
        print(f"错误：{e}")
    print(f"已写入：{f.parent / 'progress.html'}")
    sys.exit(1 if errors else 0)


def cmd_index(args):
    root = case_root(args.root)
    rows = []
    for f in sorted(root.glob("*/case.json")):
        try:
            case = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rows.append((f.parent.name, "（case.json 无法解析）", "", "", "", "", "", "", "", ""))
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
            f"{m['分歧·用户对']} / {m['分歧·AI 对']} / {m['分歧数']}" if m["分歧数"] else "",
            "有" if errors else "",
        ))
    L = ["# 问题结构案例库", "",
         "> 由 `case_tool.py index` 自动生成。每个案例的真源是各自目录下的 `case.json`，`tree.md` 与 `graph.canvas` 由 `render` 生成。",
         "", f"共 {len(rows)} 个案例。", "",
         "| 案例 | 标题 | 状态 | 查询类型 | 近似母题 | 领域 | 记录轮数 | 用户纠正 | 分歧（用户对 / AI 对 / 总数） | 校验错误 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
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
    for name, fn in (("check", cmd_check), ("render", cmd_render), ("html", cmd_html)):
        p = sub.add_parser(name)
        p.add_argument("case")
        p.set_defaults(func=fn)
    p = sub.add_parser("index", help="重建 INDEX.md")
    p.add_argument("--root")
    p.set_defaults(func=cmd_index)
    args = ap.parse_args()
    args.func(args)


