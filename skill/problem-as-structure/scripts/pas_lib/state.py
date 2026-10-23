"""读视图：brief（当前状态）、next（下一步）、due（到期预测）、search（跨案例检索）、index（案例库总表）。"""
import json

from . import core_checks
from .migrate import is_v2, migrate, targets
from .render import _predictions, v2_metrics
from .store import definitions, read_json, today

STAGE_NAMES = {1: "① 拆解输入", 2: "② 识别结构", 3: "③ 调用经典方法", 4: "④ 建工作数据结构", 5: "⑤ 人机沿方法求解",
               6: "⑥ 带回原问题验证", 7: "⑦ 诊断失败原因", 8: "⑧ 价值门", 9: "⑨ 沉淀"}


def as_v2(case):
    return case if is_v2(case) else migrate(case, today())


def _live(case):
    defs = definitions()
    out, parked = [], []
    for wb in case.get("workbenches", []):
        d = defs.get(wb.get("type"), {})
        st = d.get("statuses", {})
        for n in wb.get("nodes", []):
            s = st.get(n.get("status"), {})
            label = n.get("label") or n.get("statement") or ""
            item = {"workbench": wb["id"], "id": n["id"], "status": n.get("status"), "label": label[:120]}
            if s.get("live") and n.get("kind") not in ("goal",):
                out.append(item)
            if n.get("status") == "parked":
                parked.append(item)
    return out, parked


def brief(case, limit=6000):
    case = as_v2(case)
    res = core_checks.check(case)
    live, parked = _live(case)
    pend_v = [{"id": v["id"], "target": v.get("target"), "method": v.get("method", "")[:120]}
              for v in case.get("verifications", []) if v.get("result") == "pending"]
    preds = [{"claim": c, "settle_by": p.get("settle_by"), "state": s} for c, p, s in _predictions(case) if s != "已结算"]
    data = {
        "id": case.get("id"), "title": case.get("title"), "status": case.get("status"),
        "goal": case["problem"].get("goal"), "success_test": case["problem"].get("success_test"),
        "fast_path": case["problem"].get("fast_path"),
        "hard_constraints": [f"{c['id']} {c['text']}" for c in case.get("constraints", []) if c.get("kind") == "hard"],
        "soft_constraints": [f"{c['id']} {c['text']}" for c in case.get("constraints", []) if c.get("kind") == "soft"],
        "accepted_archetypes": [{"id": a["id"], "name": a.get("name"), "role": a.get("role"), "workbench": a.get("workbench")}
                                for a in case.get("archetypes", []) if a.get("status") == "accepted"],
        "workbenches": [{"id": w["id"], "type": w.get("type"), "nodes": len(w.get("nodes", []))} for w in case.get("workbenches", [])],
        "live": live, "parked": parked, "pending_verifications": pend_v, "open_predictions": preds,
        "pending_questions": case.get("pending", []),
        "errors": [f"{f['id']}：{f['message']}" for f in res.errors],
        "rules": [f"{f['id']}：{f['message']}" for f in res.rules],
        "last_round": (case.get("rounds") or [{}])[-1].get("n"),
    }
    text = json.dumps(data, ensure_ascii=False)
    if len(text) > limit:
        for k in ("live", "parked", "pending_verifications", "pending_questions", "rules"):
            while len(json.dumps(data, ensure_ascii=False)) > limit and len(data[k]) > 3:
                data[k] = data[k][:-1]
                data["truncated"] = True
    return data


def next_actions(case):
    """按状态给出可做的下一步（阶段、动作、理由）。方法规则（规则·）优先。"""
    case = as_v2(case)
    res = core_checks.check(case)
    acts = []

    def A(stage, action, why):
        acts.append({"stage": STAGE_NAMES[stage], "action": action, "why": why})

    for f in res.errors:
        A(7 if f["id"].startswith("VF") else 1, "先修正校验错误", f"{f['id']}：{f['message']}")
    for f in res.rules:
        stage = {"CT-15": 7, "CT-16": 5, "CT-13": 5, "CT-14": 5, "AR-02": 2, "AG-06": 9, "AG-08": 6, "CO-03": 1}.get(f["id"], 5)
        A(stage, f.get("action") or "按方法规则处理", f"{f['id']}：{f['message']}")
    p = case["problem"]
    if not p.get("goal") or not p.get("success_test"):
        A(1, "写目标和成功检验（要能在现实里观察到）", "problem.goal 或 success_test 为空")
    if not case.get("constraints"):
        A(1, "收集约束：每句话分成五类，硬约束请用户确认", "还没有约束")
    acc = [a for a in case.get("archetypes", []) if a.get("status") == "accepted"]
    if not acc and not p.get("fast_path"):
        A(2, "从母题索引挑 1–3 个候选，写表面线索、结构检查、区分检验，再选定", "还没有接受的母题")
    have = {w.get("type") for w in case.get("workbenches", [])}
    for a in acc:
        if a.get("workbench") and a["workbench"] not in have:
            A(4, f"按母题 {a['id']} 建 {a['workbench']} 工作结构", "母题已选定，但它规定的工作结构还没建")
    live, parked = _live(case)
    verified = {t for v in case.get("verifications", []) if v.get("result") in ("pass", "fail") for t in targets(v)}
    untested = [n for n in live if n["id"] not in verified and n["status"] in ("open", "chosen", "available")]
    if untested:
        A(6, "把活的候选带回原问题验证（验证便宜时一次验证多个）", "待验证：" + "、".join(n["id"] for n in untested[:8]))
    for c, pr, s in _predictions(case):
        if s == "到期未结算":
            A(6, f"结算预测 {c}：pas settle", f"结算日 {pr.get('settle_by')} 已过")
    chosen = [n for n in live if n["status"] == "chosen"]
    if chosen and case.get("status") not in ("solved",):
        passed = [n for n in chosen if any(n["id"] in targets(v) and v.get("result") == "pass" for v in case.get("verifications", []))]
        if passed:
            A(8, "把方案写成提案（pas apply --dry-run 生成差异预览），连同代价、备选、未核实之处请用户决定", "选定方案已验证通过")
    if case.get("status") == "solved" and not (case.get("retro") or {}).get("lessons"):
        A(9, "写复盘：每条经验 2–4 句，带具体数字，只提一条可复用的教训", "已解决但没写经验")
    if not acts:
        A(5, "继续沿方法路径展开或比较候选", "没有待处理的规则提醒")
    return {"case": case.get("id"), "actions": acts}


def _cases(root):
    for f in sorted(root.glob("*/case.json")):
        try:
            yield f, as_v2(read_json(f))
        except Exception as e:  # noqa: BLE001
            yield f, {"_error": str(e)}


def due(root, days=0):
    import datetime
    horizon = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
    out = []
    for f, c in _cases(root):
        if "_error" in c:
            continue
        for cid, p, s in _predictions(c):
            if s != "已结算" and p.get("settle_by", "9999") <= horizon:
                out.append({"case": c.get("id"), "claim": cid, "settle_by": p.get("settle_by"), "state": s, "statement": p.get("statement")})
    return {"horizon": horizon, "due": out}


def search(root, query):
    words = [w.lower() for w in query.split() if w]
    hits = []

    def match(text):
        t = (text or "").lower()
        return all(w in t for w in words)

    for f, c in _cases(root):
        if "_error" in c:
            continue
        cid = c.get("id")
        for k in c.get("conflicts", []):
            text = k.get("common_cause", "") + " " + " ".join(k.get("conditions", []))
            if match(text):
                hits.append({"case": cid, "kind": "冲突核", "id": k["id"], "text": text[:200]})
        r = c.get("retro") or {}
        for x in r.get("lessons", []):
            t = x if isinstance(x, str) else x.get("text", "")
            if match(t):
                hits.append({"case": cid, "kind": "经验", "text": t[:200]})
        for x in r.get("reusable_constraints", []):
            if match(x):
                hits.append({"case": cid, "kind": "可复用约束", "text": x[:200]})
        for x in r.get("unmatched", []):
            if match(x):
                hits.append({"case": cid, "kind": "待补母题", "text": x[:200]})
        for wb in c.get("workbenches", []):
            for n in wb.get("nodes", []):
                if n.get("status") in ("pruned", "failed", "parked"):
                    t = " ".join([n.get("label", "") or n.get("statement", ""), n.get("note", "")] + n.get("conditions", []))
                    if match(t):
                        hits.append({"case": cid, "kind": f"出局（{n['status']}）", "id": n["id"], "text": t[:200], "conditions": n.get("conditions", [])})
        for a in c.get("archetypes", []):
            t = " ".join([a.get("name", ""), a.get("mapping", ""), a.get("role", "")])
            if match(t):
                hits.append({"case": cid, "kind": "母题", "id": a["id"], "text": t[:200], "status": a.get("status")})
    return {"query": query, "hits": hits}


def index_md(root):
    rows = []
    for f, c in _cases(root):
        if "_error" in c:
            rows.append((f.parent.name, "（case.json 无法解析）", "", "", "", "", "", "", "", "", ""))
            continue
        res = core_checks.check(c)
        m = v2_metrics(c)
        rounds = c.get("rounds", [])
        dis = c.get("disagreements", [])
        ur = sum(1 for d in dis if d.get("resolution") == "user_right")
        ar = sum(1 for d in dis if d.get("resolution") == "ai_right")
        rows.append((
            f"[{c.get('id', f.parent.name)}]({f.parent.name}/tree.md)",
            c.get("title", ""),
            {"open": "进行中", "converging": "收敛中", "solved": "已解决", "parked": "暂停", "abandoned": "放弃"}.get(c.get("status"), c.get("status", "")),
            "；".join(a.get("name", "") for a in c.get("archetypes", []) if a.get("status") == "accepted"),
            m["工作结构类型"],
            "；".join(c.get("domain", [])),
            len(rounds),
            sum(1 for r in rounds if r.get("correction")),
            f"{ur} / {ar} / {len(dis)}" if dis else "",
            f"{m['预测·到期未结算']} / {m['预测数']}" if m["预测数"] else "",
            "有" if res.errors else "",
        ))
    from .v1core import md_cell
    L = ["# 问题结构案例库", "",
         "> 由 `pas index` 自动生成。每个案例的真源是各自目录下的 `case.json`。", "",
         f"共 {len(rows)} 个案例。", "",
         "| 案例 | 标题 | 状态 | 母题 | 工作结构 | 领域 | 轮数 | 用户纠正 | 分歧（用户对 / AI 对 / 总数） | 预测（到期未结算 / 总数） | 校验错误 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    L += ["| " + " | ".join(md_cell(x) for x in r) + " |" for r in rows]
    return "\n".join(L) + "\n", len(rows)
