"""v1 ⇄ v2 的转换。

- migrate(v1) -> v2：无损升级（docs/migration_v1_to_v2.md）。
- v1_view(v2) -> v1 形状的视图：给 v1core 做校验和渲染用。对迁移来的案例，
  v1_view(migrate(c)) 与 c 语义相同（只有 links 里论断边的位置可能不同），这是差分测试的基础。
"""
import copy

PRIMARY = ("candidate_tree", "argument_graph")


def is_v2(case):
    return case.get("schema_version") == 2


def migrate(v1, date):
    c = copy.deepcopy(v1)
    out = {}
    claims = c.pop("claims", None)
    links = c.get("links", [])
    claim_ids = {x.get("id") for x in (claims or [])}
    node_links = [lk for lk in links if not (lk.get("from") in claim_ids and lk.get("to") in claim_ids)]
    claim_links = [lk for lk in links if lk.get("from") in claim_ids and lk.get("to") in claim_ids]
    accepted = [a["id"] for a in c.get("archetypes", []) if a.get("status") == "active"]
    for a in c.get("archetypes", []):
        if a.get("status") == "active":
            a["status"] = "accepted"
    wbs = []
    nodes = c.get("nodes", [])
    wbs.append({"id": "W1", "type": "candidate_tree", "type_version": 1, "archetypes": accepted, "nodes": nodes})
    if claims:
        cn = []
        for x in claims:
            y = {"id": x["id"], "kind": "claim", "status": x.get("status", "current")}
            for k, v in x.items():
                if k not in ("id", "status"):
                    y[k] = v
            if "status" not in x:
                y["_status_default"] = True
            cn.append(y)
        wbs.append({"id": "W2", "type": "argument_graph", "type_version": 1, "nodes": cn, "edges": claim_links})
    for k, v in c.items():
        if k == "schema_version":
            out[k] = 2
            out["migration"] = {"from": 1, "date": date}
        elif k == "nodes":
            out["workbenches"] = wbs
        elif k == "links":
            out[k] = node_links
        else:
            out[k] = v
    if "workbenches" not in out:
        out["workbenches"] = wbs
    _strip_private(out)
    return out


def _strip_private(case):
    # _status_default 只在内存中记录"v1 里没写 status"，写盘前存到 history 外的约定字段里没有必要；
    # 论断 status 缺省就是 current，渲染时等价，所以直接去掉。
    for wb in case.get("workbenches", []):
        for n in wb.get("nodes", []):
            n.pop("_status_default", None)


def primary(case, wtype):
    for wb in case.get("workbenches", []):
        if wb.get("type") == wtype:
            return wb
    return None


def v1_view(case):
    """把 v2 案例投影成 v1 形状，供 v1core 使用。"""
    if not is_v2(case):
        return case
    v = {}
    ct = primary(case, "candidate_tree")
    ag = primary(case, "argument_graph")
    for k, val in case.items():
        if k == "schema_version":
            v[k] = 1
        elif k == "migration":
            continue
        elif k == "workbenches":
            v["nodes"] = copy.deepcopy(ct["nodes"]) if ct else []
        elif k == "links":
            v[k] = copy.deepcopy(val) + (copy.deepcopy(ag.get("edges", [])) if ag else [])
        elif k == "archetypes":
            arr = copy.deepcopy(val)
            for a in arr:
                if a.get("status") == "accepted":
                    a["status"] = "active"
            v[k] = arr
        elif k == "verifications":
            v[k] = _expand_targets(val)
        else:
            v[k] = copy.deepcopy(val)
    if "links" not in v and ag and ag.get("edges"):
        v["links"] = copy.deepcopy(ag["edges"])
    if ag:
        cls = []
        for n in ag["nodes"]:
            x = {k: val for k, val in n.items() if k != "kind"}
            cls.append(x)
        v["claims"] = cls
    # 跨工作结构的连接（例如依赖图的中继 same_as 候选树的子目标）不交给 v1 规则，由 v2 的 CO-07 检查
    vn = {n["id"] for n in v.get("nodes", [])}
    vc = {x["id"] for x in v.get("claims", [])}
    keep, cross = [], []
    for lk in v.get("links", []):
        f, t = lk.get("from"), lk.get("to")
        (keep if (f in vn and t in vn) or (f in vc and t in vc) else cross).append(lk)
    if "links" in v:
        v["links"] = keep
    v["_cross_links"] = cross
    if not ct:
        # v1 要求恰好一个根；没有候选树时放一个只读的占位根，避免 v1 规则误报
        v["nodes"] = [{"id": "N0", "label": case.get("title", ""), "parent": None, "kind": "goal", "status": "open"}]
        v["_no_candidate_tree"] = True
    return v


def _expand_targets(vs):
    out = []
    for x in vs:
        t = x.get("target")
        if isinstance(t, list):
            for i, tid in enumerate(t):
                y = copy.deepcopy(x)
                y["target"] = tid
                if i:
                    y["id"] = f"{x['id']}+{tid}"
                out.append(y)
        else:
            out.append(copy.deepcopy(x))
    return out


def targets(v):
    t = v.get("target")
    return t if isinstance(t, list) else [t]
