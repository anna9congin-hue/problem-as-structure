"""通用工作结构引擎：按定义文件校验一个 workbench。

返回 findings：[(level, inv_id, message, action)]，level 取 error / rule / remind。
对 candidate_tree 与 argument_graph 的"主"工作结构，来源为 v1 的不变量由 v1core 执行（逐字一致），
这里跳过，只执行来源为 v2 的不变量（skip_v1=True）。
"""
import importlib

from .jsonschema_lite import validate
from .migrate import targets

LEVELS = ("error", "rule", "remind")


def _ids(case, kind):
    if kind == "evidence":
        return {e["id"] for e in case.get("evidence", [])}
    if kind == "constraint":
        return {c["id"] for c in case.get("constraints", [])}
    if kind == "verification":
        return {v["id"] for v in case.get("verifications", [])}
    if kind == "archetype":
        return {a["id"] for a in case.get("archetypes", [])}
    if kind in ("node", "claim"):
        return {n["id"] for wb in case.get("workbenches", []) for n in wb.get("nodes", [])}
    raise ValueError(kind)


def _verifs(case, nid, result=None):
    return [v for v in case.get("verifications", []) if nid in targets(v) and (result is None or v.get("result") == result)]


def _as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _graph(wb, edge):
    """边 -> 邻接表。edge='parent' 表示用节点的 parent 字段（子 -> 父）。"""
    adj = {n["id"]: [] for n in wb.get("nodes", [])}
    if edge == "parent":
        for n in wb.get("nodes", []):
            if n.get("parent") not in (None, ""):
                adj.setdefault(n["id"], []).append(n["parent"])
    else:
        for e in wb.get("edges", []):
            if e.get("type") == edge:
                adj.setdefault(e["from"], []).append(e["to"])
    return adj


def _sccs(adj):
    index, low, stack, on, out, i = {}, {}, [], set(), [], [0]

    def strong(v):
        index[v] = low[v] = i[0]
        i[0] += 1
        stack.append(v)
        on.add(v)
        for w in adj.get(v, []):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            out.append(comp)

    for v in list(adj):
        if v not in index:
            strong(v)
    return out


def _cyclic_components(adj):
    comps = []
    for c in _sccs(adj):
        if len(c) > 1 or (c and c[0] in adj.get(c[0], [])):
            comps.append(set(c))
    return comps


def check_shell(case, wb, d, F):
    """WB-02..WB-04：kind、字段、状态、转移、边。"""
    wid = wb["id"]
    nt, st, et = d["node_types"], d["statuses"], d["edge_types"]
    N = {n["id"]: n for n in wb.get("nodes", [])}
    for n in wb.get("nodes", []):
        nid, kind = n.get("id"), n.get("kind")
        if kind not in nt:
            F("error", "WB-02", f"{wid} 的节点 {nid} 的 kind `{kind}` 不在 {d['id']} 定义里（{sorted(nt)}）", "")
        else:
            spec = {"type": "object", "properties": nt[kind]["properties"], "required": nt[kind].get("required", [])}
            for path, msg in validate(n, spec):
                F("error", "WB-02", f"{wid} 的节点 {nid}{path[1:]}：{msg}", "")
        if n.get("status") not in st:
            F("error", "WB-03", f"{wid} 的节点 {nid} 的 status `{n.get('status')}` 不在 {d['id']} 定义里（{sorted(st)}）", "")
        tr = d.get("transitions", "any")
        if tr != "any":
            allowed = {tuple(x) for x in tr}
            seq = [h.get("status") for h in n.get("history", []) if h.get("status")]
            for a, b in zip(seq, seq[1:]):
                if a != b and (a, b) not in allowed:
                    F("error", "WB-03", f"{wid} 的节点 {nid} 的状态从 {a} 变到 {b}，{d['id']} 不允许这种转移", "")
    for e in wb.get("edges", []):
        t = e.get("type")
        if t not in et:
            F("error", "WB-04", f"{wid} 的边 {e.get('from')}→{e.get('to')} 的类型 `{t}` 不在 {d['id']} 定义里（{sorted(et)}）", "")
            continue
        for end in ("from", "to"):
            if e.get(end) not in N:
                F("error", "WB-04", f"{wid} 的边 {e.get('from')}→{e.get('to')} 的 {end} 端不存在", "")
            elif et[t].get(end) and N[e[end]].get("kind") not in et[t][end]:
                F("error", "WB-04", f"{wid} 的边 {e['from']}→{e['to']}：{end} 端的 kind 必须是 {et[t][end]}", "")
        attrs = et[t].get("attrs")
        if attrs:
            for k, spec in attrs.items():
                if k in e:
                    for path, msg in validate(e[k], spec):
                        F("error", "WB-04", f"{wid} 的边 {e.get('from')}→{e.get('to')} 的 {k}：{msg}", "")
    if d.get("extra") and wb.get("extra") is not None:
        for path, msg in validate(wb["extra"], d["extra"]):
            F("error", "WB-02", f"{wid}.extra{path[1:]}：{msg}", "")


def run_invariants(case, wb, d, F, skip_v1=False):
    N = {n["id"]: n for n in wb.get("nodes", [])}
    C = {c["id"]: c for c in case.get("constraints", [])}
    EV = {e["id"]: e for e in case.get("evidence", [])}
    for inv in d["invariants"]:
        if skip_v1 and str(inv.get("origin", "")).startswith("v1"):
            continue
        rule, p, lvl, iid = inv["rule"], inv.get("params", {}), inv["level"], inv["id"]
        msg, act = inv["message"], inv.get("action", "")

        def out(text, level=lvl):
            F(level, iid, f"{wb['id']}：{text}", act)

        if rule == "tree":
            adj = _graph(wb, p["edge"])
            if p["edge"] == "parent":
                roots = [n for n in wb["nodes"] if n.get("parent") in (None, "")]
                bad_parent = [n["id"] for n in wb["nodes"] if n.get("parent") not in (None, "") and n["parent"] not in N]
            else:
                has_parent = {t for vs in adj.values() for t in vs}
                roots = [n for n in wb["nodes"] if n["id"] not in {e["to"] for e in wb.get("edges", []) if e.get("type") == p["edge"]}]
                bad_parent = []
                _ = has_parent
            if len(roots) != 1 or roots[0].get("kind") != p.get("root_kind", roots[0].get("kind") if roots else None):
                out(f"{msg}（根：{[r['id'] for r in roots]}）")
            if bad_parent:
                out(f"{msg}（parent 不存在：{bad_parent}）")
            if _cyclic_components(adj):
                out(f"{msg}（有环）")
        elif rule == "acyclic":
            cyc = _cyclic_components(_graph(wb, p["edge"]))
            if cyc:
                out(f"{msg}：{[sorted(c) for c in cyc]}")
        elif rule == "cycles_marked":
            marked = [set(x) for x in (wb.get("extra") or {}).get(p["marks"], [])]
            for comp in _cyclic_components(_graph(wb, p["edge"])):
                if not any(comp <= m or m == comp for m in marked):
                    out(f"{msg}：{sorted(comp)}")
        elif rule == "not_reaches":
            marked = set().union(*[set(x) for x in (wb.get("extra") or {}).get("cycles", [])]) if (wb.get("extra") or {}).get("cycles") else set()
            adj = _graph(wb, p["edge"])
            for n in wb["nodes"]:
                if n.get("kind") != p["from_kind"]:
                    continue
                seen, stack = set(), list(adj.get(n["id"], []))
                while stack:
                    u = stack.pop()
                    if u in seen:
                        continue
                    seen.add(u)
                    stack.extend(adj.get(u, []))
                hit = sorted(seen & marked)
                if hit:
                    out(f"{msg}：{n['id']} → {hit}")
        elif rule == "status_requires":
            for n in wb["nodes"]:
                if n.get("status") != p["status"]:
                    continue
                ok = True
                if "field_nonempty" in p and not n.get(p["field_nonempty"]):
                    ok = False
                if "any_nonempty" in p and not any(n.get(k) for k in p["any_nonempty"]):
                    ok = False
                if "verification" in p and not _verifs(case, n["id"], p["verification"]):
                    ok = bool(p.get("or_field") and n.get(p["or_field"]))
                if not ok:
                    level = lvl
                    if p.get("error_only_if_case_status") and case.get("status") != p["error_only_if_case_status"]:
                        level = "remind"
                    out(f"{n['id']} {msg}", level)
        elif rule == "ref_exists":
            ids = _ids(case, p["target"])
            for n in wb["nodes"]:
                for r in _as_list(n.get(p["field"])):
                    if r not in ids:
                        out(f"{n['id']} {msg}：{r}")
        elif rule == "ref_filter":
            for n in wb["nodes"]:
                if n.get("status") != p["status"]:
                    continue
                for r in _as_list(n.get(p["field"])):
                    c = C.get(r)
                    if c is None:
                        out(f"{n['id']} 引用了不存在的约束 {r}")
                        continue
                    if any(c.get(k) != v for k, v in (p.get("only_if") or {}).items()):
                        continue
                    must = p.get("must", {})
                    bad = False
                    for k, v in must.items():
                        if k == "world_fact_backed":
                            bad |= not any(EV.get(e, {}).get("verified") for e in c.get("evidence", []))
                        elif c.get(k) != v:
                            bad = True
                    if bad:
                        out(f"{n['id']} {msg}（{r}）")
        elif rule == "evidence_verified":
            for n in wb["nodes"]:
                if n.get("status") == p["status"]:
                    for r in _as_list(n.get(p["field"])):
                        if r in EV and not EV[r].get("verified"):
                            out(f"{n['id']} {msg}（{r}）")
        elif rule == "children_prob":
            kids = {}
            for n in wb["nodes"]:
                if n.get("parent"):
                    kids.setdefault(n["parent"], []).append(n)
            for n in wb["nodes"]:
                if n.get("kind") != p["parent_kind"]:
                    continue
                ch = [k for k in kids.get(n["id"], []) if k.get("kind") == p["child_kind"]]
                total = 0.0
                for k in ch:
                    if isinstance(k.get(p["field"]), (int, float)):
                        total += k[p["field"]]
                    elif not k.get(p["unknown_flag"]):
                        out(f"{k['id']} {msg}")
                if total > 1 + 1e-9:
                    out(f"{n['id']} 下 {msg}（和为 {round(total, 6)}）")
        elif rule == "field_present":
            if "workbench_field" in p:
                if wb.get(p["workbench_field"]) == p.get("equals", True):
                    out(msg)
                continue
            for n in wb["nodes"]:
                if p.get("statuses") and n.get("status") not in p["statuses"]:
                    continue
                if p.get("kinds") and n.get("kind") not in p["kinds"]:
                    continue
                if p["field"] not in n:
                    out(f"{n['id']} {msg}")
        elif rule == "hook":
            mod = importlib.import_module(f"pas_lib.checks.{p['module']}")
            for level, text in getattr(mod, p["function"])(case, wb, d):
                out(text, level or lvl)
        else:
            F("error", "WB-01", f"{wb['id']}：定义 {d['id']} 用了未知的规则 {rule}", "")
