"""渲染 tree.md、graph.canvas、progress.html。

v1 的部分（候选树、论断等）直接用 v1core 在 v1 视图上渲染，逐字不变；
v2 的部分作为独立小节插在"## 方案"之前，小节标题见 V2_SECTIONS，差分测试据此剥离。
v2 的校验发现以"ID：消息"的形式接在 v1 的错误与提醒之后。
"""
import datetime
import html as _html
import json

from . import v1core
from .migrate import PRIMARY, primary, targets, v1_view
from .store import definitions

V2_SECTIONS = ("## 工作结构", "## 母题检查", "## 预测账本", "## 失败诊断", "## v2 指标")
HTML_BEGIN, HTML_END = "<!-- pas-v2:begin -->", "<!-- pas-v2:end -->"
CAUSE = {"missing_constraint": "漏了约束", "archetype_assumption": "母题假设不成立", "implementation": "实现错误"}


def clean_view(case):
    v = v1_view(case)
    return {k: val for k, val in v.items() if not k.startswith("_")}


def _cell(x):
    return v1core.md_cell(x)


def _wb_lines(wb, d):
    st = d["statuses"]
    lab = d["render"].get("label_field", "label")
    mark = lambda n: st.get(n.get("status"), {}).get("mark", "[?]")  # noqa: E731
    name = lambda n: st.get(n.get("status"), {}).get("label", n.get("status"))  # noqa: E731
    kinds = d["node_types"]
    out = []
    if d["render"]["as"] == "tree":
        kids = {}
        for n in wb["nodes"]:
            kids.setdefault(n.get("parent") or None, []).append(n)

        def walk(n, depth):
            extra = []
            for f in d["render"].get("show", []):
                if f not in ("status", lab) and f in n:
                    extra.append(f"{f}={n[f]}")
            if n.get("kind") == "scenario" and "p" not in n and n.get("p_unknown"):
                extra.append("p=?")
            k = kinds.get(n.get("kind"), {}).get("label", n.get("kind"))
            line = f"{'  ' * depth}{mark(n)} {n['id']} 〔{k}〕{n.get(lab, '')} —— {name(n)}"
            if extra:
                line += "（" + "，".join(extra) + "）"
            if n.get("note"):
                line += f"：{n['note']}"
            out.append(line)
            for c in kids.get(n["id"], []):
                walk(c, depth + 1)

        for r in kids.get(None, []):
            walk(r, 0)
    else:
        for n in wb["nodes"]:
            k = kinds.get(n.get("kind"), {}).get("label", n.get("kind"))
            extra = [f"{f}={n[f]}" for f in d["render"].get("show", []) if f not in ("status", lab) and f in n]
            line = f"{mark(n)} {n['id']} 〔{k}〕{n.get(lab, '')} —— {name(n)}"
            if extra:
                line += "（" + "，".join(str(x) for x in extra) + "）"
            out.append(line)
        et = d["edge_types"]
        for e in wb.get("edges", []):
            out.append(f"    {e['from']} —{et.get(e['type'], {}).get('label', e['type'])}→ {e['to']}")
        for cyc in (wb.get("extra") or {}).get("cycles", []):
            out.append("    ↻ " + " → ".join(cyc + cyc[:1]))
    return out


def v2_sections(case, result):
    defs = definitions()
    L = []
    wbs = case.get("workbenches", [])
    L += ["## 工作结构", "", "> v2：工作结构由母题决定，类型见 `assets/workbenches/`。", ""]
    for wb in wbs:
        d = defs.get(wb.get("type"))
        title = f"### {wb['id']} {wb.get('label') or (d['label'] if d else wb.get('type'))}（{wb.get('type')} v{wb.get('type_version')}）"
        if wb.get("archetypes"):
            title += " · 母题 " + "、".join(wb["archetypes"])
        L += [title, ""]
        if wb.get("type") in PRIMARY and primary(case, wb["type"]) is wb:
            L += ["见上文「解空间」。" if wb["type"] == "candidate_tree" else "见上文「论断」。", ""]
            continue
        if d is None:
            L += ["（没有定义文件）", ""]
            continue
        L += ["```text"] + _wb_lines(wb, d) + ["```", ""]
        if d["render"].get("legend"):
            L += [f"图例：{d['render']['legend']}", ""]
        if wb.get("standardize_pending"):
            L += ["> 待标准化：同样的用法在 2 个以上案例出现时，整理成定义文件。", ""]
    arch = case.get("archetypes", [])
    if arch:
        L += ["## 母题检查", "", "| ID | 母题 | 状态 | 负责 | 表面线索 | 结构检查 | 区分检验 | 对手先行 | 工作结构 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for a in arch:
            dt = a.get("discriminating_test") or {}
            adv = a.get("adversary") or {}
            dts = (dt.get("test", "") + (f" → {dt['result']}" if dt.get("result") else "")) if dt else ""
            advs = (adv.get("tried", "") + ("；找到反例：" + adv.get("counterexample", "") if adv.get("found") else ("；未找到反例" if adv else ""))) if adv else ""
            L.append(f"| {a['id']} | {_cell(a.get('name'))} | {_cell(a.get('status'))} | {_cell(a.get('role'))} | {_cell(a.get('surface_cues'))} | "
                     f"{_cell(a.get('structural_checks'))} | {_cell(dts)} | {_cell(advs)} | {_cell(a.get('workbench'))} |")
        L.append("")
    preds = _predictions(case)
    if preds:
        L += ["## 预测账本", "", "| 论断 | 预测 | 证伪条件 | 结算日 | p | 事件 | 结果 | 状态 |", "|---|---|---|---|---|---|---|---|"]
        for cid, p, state in preds:
            ev = p.get("event") or {}
            evs = f"{ev.get('date', '')} {ev.get('label', '')}；好：{ev.get('if_good', '—')}；坏：{ev.get('if_bad', '—')}" if ev else ""
            oc = p.get("outcome") or {}
            L.append(f"| {cid} | {_cell(p.get('statement'))} | {_cell(p.get('falsifier'))} | {_cell(p.get('settle_by'))} | "
                     f"{_cell(p.get('p'))} | {_cell(evs)} | {_cell(oc.get('result'))} | {state} |")
        L.append("")
    fails = [v for v in case.get("verifications", []) if v.get("result") == "fail"]
    if fails:
        L += ["## 失败诊断", "", "| 验证 | 对象 | 原因 | 违反的约束 / 母题 | 验证器 | 说明 |", "|---|---|---|---|---|---|"]
        for v in fails:
            vf = v.get("verifier") or {}
            who = v.get("violated") or v.get("archetype") or ""
            L.append(f"| {v['id']} | {_cell(v.get('target'))} | {_cell(CAUSE.get(v.get('cause'), v.get('cause') or '未写'))} | {_cell(who)} | "
                     f"{_cell(vf.get('class'))} | {_cell(v.get('note'))} |")
        L.append("")
    L += ["## v2 指标", "", "| 指标 | 值 |", "|---|---|"]
    for k, val in v2_metrics(case).items():
        L.append(f"| {k} | {_cell(val)} |")
    L.append("")
    return L


def _predictions(case, today=None):
    today = today or datetime.date.today().isoformat()
    out = []
    for wb in case.get("workbenches", []):
        for n in wb.get("nodes", []):
            p = n.get("prediction")
            if not p:
                continue
            if p.get("outcome"):
                state = "已结算"
            elif p.get("settle_by", "9999") <= today:
                state = "到期未结算"
            else:
                state = "待结算"
            out.append((n["id"], p, state))
    return out


def v2_metrics(case):
    wbs = case.get("workbenches", [])
    m = {"工作结构数": len(wbs), "工作结构类型": "、".join(sorted({w.get("type", "") for w in wbs})) or "—"}
    fails = [v for v in case.get("verifications", []) if v.get("result") == "fail"]
    for k, lab in CAUSE.items():
        m[f"失败·{lab}"] = sum(1 for v in fails if v.get("cause") == k)
    m["失败·未写原因"] = sum(1 for v in fails if not v.get("cause"))
    stages = {}
    for r in case.get("rounds", []):
        for s in r.get("stages", []):
            stages[s] = stages.get(s, 0) + 1
    m["各阶段涉及轮数"] = "；".join(f"{'①②③④⑤⑥⑦⑧⑨'[s - 1]} {c}" for s, c in sorted(stages.items())) or "—"
    preds = _predictions(case)
    m["预测数"] = len(preds)
    m["预测·已结算"] = sum(1 for _, _, s in preds if s == "已结算")
    m["预测·到期未结算"] = sum(1 for _, _, s in preds if s == "到期未结算")
    scored = [(p["p"], 1.0 if p["outcome"]["result"] == "true" else 0.0) for _, p, s in preds
              if s == "已结算" and isinstance(p.get("p"), (int, float)) and p["outcome"].get("result") in ("true", "false")]
    m["Brier"] = round(sum((a - b) ** 2 for a, b in scored) / len(scored), 4) if scored else "—"
    cred = {}
    for d in case.get("disagreements", []):
        dom = d.get("domain") or "未分类"
        c = cred.setdefault(dom, {"user_right": 0, "ai_right": 0, "both_partly": 0, "total": 0})
        c["total"] += 1
        if d.get("resolution") in c:
            c[d["resolution"]] += 1
    m["可信度（用户对 / AI 对 / 各对一部分 / 总数）"] = "；".join(
        f"{k}：{v['user_right']}/{v['ai_right']}/{v['both_partly']}/{v['total']}" for k, v in sorted(cred.items())) or "—"
    return m


def render_md(case, result):
    view = clean_view(case)
    e2, w2 = result.v2_lines()
    text = v1core.render_md(view, result.v1_errors + e2, result.v1_warnings + w2)
    if v1_view(case).get("_no_candidate_tree"):
        start = text.index("## 解空间")
        end = text.index("\n## ", start + 3)
        text = text[:start] + "## 解空间\n\n本案例没有候选树，见下文「工作结构」。\n" + text[end:]
    extra = "\n".join(v2_sections(case, result)) + "\n"
    i = text.index("## 方案")
    return text[:i] + extra + text[i:]


def render_canvas(case):
    view = clean_view(case)
    cv = v1core.render_canvas(view)
    defs = definitions()
    if v1_view(case).get("_no_candidate_tree"):
        cv["nodes"] = [n for n in cv["nodes"] if n.get("id") != "N0"]
        cv["edges"] = [e for e in cv["edges"] if e.get("fromNode") != "N0" and e.get("toNode") != "N0"]
    ys = [n["y"] + n.get("height", 0) for n in cv["nodes"]] or [0]
    y0 = max(ys) + 200
    for wb in case.get("workbenches", []):
        if wb.get("type") in PRIMARY and primary(case, wb["type"]) is wb:
            continue
        d = defs.get(wb.get("type"))
        if not d:
            continue
        st = d["statuses"]
        x = 0
        for n in wb["nodes"]:
            cn = {"id": n["id"], "type": "text", "x": x, "y": y0, "width": 300, "height": 110,
                  "text": f"**{n['id']} {n.get(d['render'].get('label_field', 'label'), '')}**\n{st.get(n.get('status'), {}).get('label', '')}"}
            if st.get(n.get("status"), {}).get("color"):
                cn["color"] = st[n["status"]]["color"]
            cv["nodes"].append(cn)
            x += 360
        for i, e in enumerate(wb.get("edges", [])):
            cv["edges"].append({"id": f"{wb['id']}-e{i}", "fromNode": e["from"], "fromSide": "bottom", "toNode": e["to"], "toSide": "top",
                                "label": d["edge_types"].get(e["type"], {}).get("label", e["type"])})
        if wb.get("type") in ("candidate_tree", "decision_tree"):
            for n in wb["nodes"]:
                if n.get("parent"):
                    cv["edges"].append({"id": f"{wb['id']}-p-{n['id']}", "fromNode": n["parent"], "fromSide": "right", "toNode": n["id"], "toSide": "left"})
        y0 += 400
    ids = {n["id"] for n in cv["nodes"]}
    for i, lk in enumerate(case.get("links", [])):
        if lk.get("from") in ids and lk.get("to") in ids and not any(e.get("id") == f"l{i}" for e in cv["edges"]):
            cv["edges"].append({"id": f"x{i}", "fromNode": lk["from"], "fromSide": "bottom", "toNode": lk["to"], "toSide": "top",
                                "label": lk.get("type", ""), "color": "6"})
    return cv


def render_html(case, result):
    view = clean_view(case)
    e2, w2 = result.v2_lines()
    page = v1core.render_html(view, result.v1_errors + e2, result.v1_warnings + w2)
    md = "\n".join(v2_sections(case, result))
    block = (f"{HTML_BEGIN}<section style=\"max-width:1100px;margin:24px auto;padding:0 16px;font:14px/1.6 system-ui,sans-serif\">"
             f"<details><summary><strong>v2：工作结构、母题检查、预测账本、失败诊断</strong></summary>"
             f"<pre style=\"white-space:pre-wrap\">{_html.escape(md)}</pre></details></section>{HTML_END}")
    i = page.rfind("</body>")
    return page[:i] + block + page[i:] if i >= 0 else page + block


def tree_lines(case):
    return v1core.tree_lines(clean_view(case))


def payload_json(case):
    return json.dumps(clean_view(case), ensure_ascii=False, sort_keys=True)
