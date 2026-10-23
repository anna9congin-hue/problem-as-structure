"""v2 的完整校验：格式（SCHEMA）+ v1 规则（经 v1core，逐字一致）+ v2 新规则 + 各工作结构的不变量。

check(case) -> Result：
  v1_errors、v1_warnings：v1core 原样输出（顺序、文字不变）
  findings：v2 新增的发现，[{level, id, message, action}]
  all：v1 与 v2 合并后的发现，每条都带不变量 ID
"""
import datetime
import re

from . import v1core
from .engine import check_shell, run_invariants
from .jsonschema_lite import validate
from .migrate import PRIMARY, is_v2, primary, targets, v1_view
from .store import core_schema, definitions

# v1 消息 → 不变量 ID（只用于给 v1 的发现打标签，不改 v1 的文字）
V1_TAGS = [
    (r"^id `.*` 重复", "CO-01"),
    (r"^缺少字段", "SCHEMA"),
    (r"^(status|problem\.query_type) `", "SCHEMA"),
    (r"规则·验收接现实", "CO-03"),
    (r"^problem\.(goal|success_test) 为空", "CO-02"),
    (r"^约束 \S+ ", "CO-04"),
    (r"^硬约束 \S+ ", "CO-04"),
    (r"^母题 \S+ 已弃用", "AR-04"),
    (r"^母题 \S+ 的 status", "SCHEMA"),
    (r"^没有 active 的近似母题", "AR-01"),
    (r"^证据 \S+ 的 type", "SCHEMA"),
    (r"^证据 \S+ 没有 source", "CO-12"),
    (r"^解空间必须恰好有 1 个根|^根节点的 kind|的 parent `|的祖先链有环", "CT-01"),
    (r"^节点 \S+ 的 (kind|status|proposed_by)", "WB-02"),
    (r"^节点 \S+ 引用了不存在的证据", "CT-02"),
    (r"被淘汰但 pruned_by 为空", "CT-03"),
    (r"的 pruned_by 引用了不存在的约束", "CT-03"),
    (r"被软偏好", "CT-04"),
    (r"被未确认的硬约束", "CT-05"),
    (r"被外部世界事实", "CT-06"),
    (r"的淘汰用了未核实的事实", "CT-07"),
    (r"被淘汰但没附事实依据", "CT-17"),
    (r"被搁置但没写原因|的 parked_by 引用了不存在的约束", "CT-08"),
    (r"规则·参照失效|规则·可行集最优|park_reference", "CT-13"),
    (r"标为失败，但没有", "CT-09"),
    (r"标为已验证，但没有", "CT-10"),
    (r"已选定，但还没有", "CT-11"),
    (r"规则·对照", "CT-14"),
    (r"^验证 \S+ 的 target|^验证 \S+ 的 result|^验证 \S+ 引用了不存在的证据", "CO-05"),
    (r"^冲突 ", "CO-06"),
    (r"^links ", "CO-07"),
    (r"^分歧 ", "CO-08"),
    (r"规则·跳级回溯", "CT-15"),
    (r"规则·重审搁置", "CT-16"),
    (r"^status=solved|^solution\.chosen|^已解决但 retro", "CO-09"),
    (r"^rounds ", "CO-11"),
    (r"^阶段 |^stages |^待决事项 |^pending |^running |^后台任务", "CO-10"),
    (r"^论断 \S+ 状态是有效，却带有 withdrawal|withdrawal\.scope", "AG-04"),
    (r"^论断 \S+ 引用了不存在的证据", "AG-02"),
    (r"^论断 \S+ 的 supersedes", "AG-03"),
    (r"^论断 ", "WB-02"),
    (r"^claims ", "SCHEMA"),
    (r"提醒·独立", "AG-05"),
    (r"规则·连带", "AG-06"),
    (r"提醒·改引用", "AG-07"),
]
_TAGS = [(re.compile(p), i) for p, i in V1_TAGS]
RULE_PREFIX = "规则·"


def tag_v1(msg):
    for rx, i in _TAGS:
        if rx.search(msg):
            return i
    return "V1"


class Result:
    def __init__(self):
        self.v1_errors, self.v1_warnings, self.findings = [], [], []

    def add(self, level, iid, message, action=""):
        f = {"level": level, "id": iid, "message": message, "action": action}
        if f not in self.findings:
            self.findings.append(f)

    @property
    def all(self):
        out = [{"level": "error", "id": tag_v1(m), "message": m, "action": "", "source": "v1"} for m in self.v1_errors]
        for m in self.v1_warnings:
            out.append({"level": "rule" if m.startswith(RULE_PREFIX) else "remind", "id": tag_v1(m), "message": m, "action": "", "source": "v1"})
        out += [dict(f, source="v2") for f in self.findings]
        return out

    @property
    def errors(self):
        return [f for f in self.all if f["level"] == "error"]

    @property
    def rules(self):
        return [f for f in self.all if f["level"] == "rule"]

    def v2_lines(self):
        """tree.md 与命令输出里 v2 发现的写法：'ID：消息（下一步：动作）'。"""
        e = [f"{f['id']}：{f['message']}" for f in self.findings if f["level"] == "error"]
        w = []
        for f in self.findings:
            if f["level"] != "error":
                pre = RULE_PREFIX if f["level"] == "rule" and not f["message"].startswith(RULE_PREFIX) else ""
                tail = f"（下一步：{f['action']}）" if f.get("action") else ""
                w.append(f"{f['id']}：{pre}{f['message']}{tail}")
        return e, w


def _date_of(x):
    s = x.get("observed_at") or x.get("date")
    return s[:10] if isinstance(s, str) else None


def check(case):
    r = Result()
    if not is_v2(case):
        r.add("error", "SCHEMA", f"schema_version 是 {case.get('schema_version')}，不是 2：先运行 pas migrate")
        r.v1_errors, r.v1_warnings = v1core.check(case)
        return r
    for path, msg in validate(case, core_schema()):
        r.add("error", "SCHEMA", f"{path}：{msg}")
    defs = definitions()
    # 一个案例最多一棵主候选树、一张主论证图（v1 视图的限制）
    for t in PRIMARY:
        n = sum(1 for wb in case.get("workbenches", []) if wb.get("type") == t)
        if n > 1:
            r.add("error", "WB-05", f"一个案例里最多一个 {t} 工作结构（现在有 {n} 个）；把它们合并，或改用其他结构")
    view = v1_view(case)
    try:
        r.v1_errors, r.v1_warnings = v1core.check(view)
    except Exception as e:  # noqa: BLE001  v1 代码遇到 v2 才有的形状时，不让整个校验崩掉
        r.add("error", "SCHEMA", f"v1 规则无法执行（{type(e).__name__}: {e}）：先修正格式错误")
    if view.get("_no_candidate_tree"):
        r.v1_warnings = [w for w in r.v1_warnings if "没有 active 的近似母题" not in w]
    _core_v2(case, r)
    for wb in case.get("workbenches", []):
        d = defs.get(wb.get("type"))
        if d is None:
            r.add("error", "WB-01", f"{wb.get('id')} 的类型 `{wb.get('type')}` 没有定义文件（assets/workbenches/{wb.get('type')}.json）")
            continue
        if wb.get("type_version") != d["version"]:
            r.add("error", "WB-01", f"{wb['id']} 用的是 {d['id']} v{wb.get('type_version')}，定义是 v{d['version']}：运行 pas migrate")

        def F(level, iid, message, action):
            r.add(level, iid, message, action)

        check_shell(case, wb, d, F)
        is_primary = wb.get("type") in PRIMARY and primary(case, wb["type"]) is wb
        run_invariants(case, wb, d, F, skip_v1=is_primary)
    return r


def _core_v2(case, r):
    defs = definitions()
    A = {a["id"]: a for a in case.get("archetypes", [])}
    C = {c["id"]: c for c in case.get("constraints", [])}
    EV = {e["id"]: e for e in case.get("evidence", [])}
    V = {v["id"]: v for v in case.get("verifications", [])}
    nodes = {n["id"]: n for wb in case.get("workbenches", []) for n in wb.get("nodes", [])}
    # CO-01：跨工作结构的节点 ID 也必须唯一（v1 只查一棵树）
    seen = {}
    for g in ("constraints", "archetypes", "evidence", "verifications", "conflicts", "disagreements"):
        for x in case.get(g, []):
            seen.setdefault(x.get("id"), g)
    for wb in case.get("workbenches", []):
        for n in wb.get("nodes", []):
            if n.get("id") in seen and seen[n["id"]] != wb["id"]:
                r.add("error", "CO-01", f"id `{n['id']}` 重复（{seen[n['id']]} 与 {wb['id']}）")
            seen[n.get("id")] = wb["id"]
    # CO-05：列表形式的 target
    for v in case.get("verifications", []):
        if isinstance(v.get("target"), list):
            for t in v["target"]:
                if t not in nodes:
                    r.add("error", "CO-05", f"验证 {v['id']} 的 target `{t}` 不存在")
    # CO-05：v1 只认候选树和论断；其他工作结构的节点也算合法 target
    others = {n for wb in case.get("workbenches", []) if wb.get("type") not in PRIMARY or primary(case, wb["type"]) is not wb for n in (x["id"] for x in wb.get("nodes", []))}
    if others:
        r.v1_errors = [e for e in r.v1_errors if not any(re.search(rf"^验证 \S+ 的 target `{re.escape(o)}` 不存在", e) for o in others)]
    # CO-07：跨工作结构的连接，两端必须存在
    for lk in v1_view(case).get("_cross_links", []):
        for end in ("from", "to"):
            if lk.get(end) not in nodes:
                r.add("error", "CO-07", f"links 的 {end} `{lk.get(end)}` 不存在：{lk}")
    # CO-10：pending.about 可以指向论断与任意工作结构节点
    r.v1_errors = [e for e in r.v1_errors if not (e.startswith("待决事项") and "的 about `" in e and re.search(r"about `([^`]+)`", e).group(1) in nodes)]
    # AR
    for a in case.get("archetypes", []):
        if a.get("status") == "accepted":
            if not a.get("structural_checks") or not a.get("discriminating_test"):
                r.add("rule", "AR-02", f"母题 {a['id']} 已接受，但没写结构检查（structural_checks）或区分检验（discriminating_test）",
                      "写出哪些结构条件真的成立，以及观察到什么就排除哪个候选母题")
            if not a.get("adversary"):
                r.add("remind", "AR-05", f"母题 {a['id']} 没做对手先行", "选定前先找一个让这个母题不成立的反例，写进 adversary")
        if a.get("workbench") and a["workbench"] not in defs:
            r.add("error", "AR-03", f"母题 {a['id']} 的 workbench `{a['workbench']}` 没有定义文件")
    # VF
    mig = (case.get("migration") or {}).get("date")
    claims_with_pred = {n["id"] for wb in case.get("workbenches", []) for n in wb.get("nodes", []) if n.get("prediction")}
    for v in case.get("verifications", []):
        vid = v["id"]
        if v.get("result") == "fail":
            if not v.get("cause"):
                legacy = mig and (v.get("date") or "0000") <= mig
                r.add("remind" if legacy else "error", "VF-01", f"验证 {vid} 失败但没写原因（cause）",
                      "三选一：missing_constraint（漏了约束）、archetype_assumption（母题假设不成立）、implementation（实现错误）")
            elif v["cause"] == "missing_constraint":
                if not v.get("violated"):
                    r.add("error", "VF-02", f"验证 {vid} 的原因是漏了约束，但没写 violated（违反的约束）")
                for c in v.get("violated", []):
                    if c not in C:
                        r.add("error", "VF-02", f"验证 {vid} 的 violated 引用了不存在的约束 {c}")
            elif v["cause"] == "archetype_assumption":
                if v.get("archetype") not in A:
                    r.add("error", "VF-02", f"验证 {vid} 的原因是母题假设不成立，但 archetype 没写或不存在")
        if (v.get("verifier") or {}).get("class") == "B" and not any(t in claims_with_pred for t in targets(v)):
            r.add("remind", "VF-03", f"验证 {vid} 是 B 类（要等结果），但没有对应带预测的论断", "在论证图里写一条带 prediction（证伪条件、结算日）的论断")
        for x in v.get("regression_of", []):
            w = V.get(x)
            if not w or w.get("result") != "pass" or (w.get("date") and v.get("date") and w["date"] > v["date"]):
                r.add("error", "VF-04", f"验证 {vid} 的 regression_of 指向 {x}，它不存在、没通过或晚于本次")
    # TM-01
    for n in nodes.values():
        dt = n.get("decided_at")
        if not dt:
            continue
        used = list(n.get("evidence", []))
        for cid in n.get("pruned_by", []):
            used += C.get(cid, {}).get("evidence", [])
        for e in used:
            d = _date_of(EV.get(e, {}))
            if d and d > dt[:10]:
                r.add("error", "TM-01", f"节点 {n['id']} 在 {dt[:10]} 做出决定，却用了 {d} 才知道的证据 {e}")
    # 快速通道
    fp = case["problem"].get("fast_path") if isinstance(case.get("problem"), dict) else None
    if fp and not fp.get("reason"):
        r.add("error", "SCHEMA", "problem.fast_path 必须写 reason")


def today():
    return datetime.date.today().isoformat()
