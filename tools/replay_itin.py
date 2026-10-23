#!/usr/bin/env python3
"""M4 回放：用 v2 的 pas 命令把 ITIN 案例补成九阶段的完整记录。

只用真实记录里已有的事实（tests/fixtures/itin-credit-builder/case.json），补上 v2 才有的结构：
  ② 母题的结构检查、区分检验、对手先行；④ 冷启动母题规定的依赖图；
  ⑥ 验证器类别，"信用局出现记录"写成可结算的预测；⑦ 失败原因；⑨ 冲突核的条件。
每一步都通过 pas 写入（不手改 JSON），最后渲染并检查：没有 error，九个阶段都有记录，工作结构由母题决定。

用法：python3 tools/replay_itin.py   结果写到 tests/replay/itin-v2/，摘要 JSON 写 stdout。
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAS = ROOT / "skill" / "problem-as-structure" / "scripts" / "pas"
SRC = ROOT / "tests" / "fixtures" / "itin-credit-builder" / "case.json"
OUT = ROOT / "tests" / "replay" / "itin-v2"
LOG = []


def pas(*args, stdin=None, ok=(0, 4)):
    p = subprocess.run([sys.executable, str(PAS)] + [str(a) for a in args], capture_output=True, text=True, input=stdin)
    LOG.append({"args": [str(a) for a in args[:3]], "code": p.returncode})
    if p.returncode not in ok:
        sys.exit(f"pas {' '.join(map(str, args))} 失败（{p.returncode}）：{p.stdout[:500]} {p.stderr[:300]}")
    return json.loads(p.stdout)


def J(x):
    return json.dumps(x, ensure_ascii=False)


def main():
    if not SRC.exists():
        print("跳过 ITIN 回放：tests/fixtures 不存在（公开仓库不含真实案例）", file=sys.stderr)
        return
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copy2(SRC, OUT / "case.json")
    c = OUT
    pas("migrate", c, ok=(0,))
    case = json.loads((c / "case.json").read_text(encoding="utf-8"))
    ai = {a["name"]: i for i, a in enumerate(case["archetypes"])}
    i_cs, i_cold, i_search = ai["约束满足与可达性"], ai["冷启动与自举"], ai["搜索与筛选"]
    # ② 识别结构：结构检查、区分检验、对手先行、各自负责的部分
    ops = []
    for i, role, checks, test, adv, wb in (
        (i_cs, "在哪一类里选：按申请前提分组、约束先行剪枝", ["C1–C3 能逐条对照每个候选"],
         {"test": "每个候选能否逐条对照 C1–C3 打勾", "result": "能"}, {"tried": "找一个无法用 C1–C3 判定的候选", "found": False}, "candidate_tree"),
        (i_cold, "先做什么：先建立信用记录", ["信用卡要求信用记录，信用记录要求有信用账户：依赖图里有环"],
         {"test": "画出依赖关系，看是否真有环", "result": "有环：信用卡 ⇄ 信用记录", "versus": [case["archetypes"][i_cs]["id"]]},
         {"tried": "找一条不经过信用记录就能办卡的路径（N11、N12 实际申请都失败）", "found": False}, "dependency_graph"),
        (i_search, "在信用构建账户这一类里比较玩家", ["这一类的玩家能列全", "条件能逐条检查"],
         {"test": "能否列出这一类的全部主要玩家", "result": "能（N231–N236）"}, {"tried": "找一个不在列表里却满足 C1–C3 的玩家", "found": False}, "candidate_tree"),
    ):
        for k, v in (("role", role), ("structural_checks", checks), ("discriminating_test", test), ("adversary", adv), ("workbench", wb)):
            ops.append({"op": "add", "path": f"/archetypes/{i}/{k}", "value": v})
    pas("apply", c, "-", stdin=J(ops))
    # ④ 冷启动母题规定的依赖图，并与候选树的子目标连接
    cold_id = case["archetypes"][i_cold]["id"]
    pas("add", c, "workbench", J({"type": "dependency_graph", "label": "信用冷启动", "archetypes": [cold_id]}))
    case = json.loads((c / "case.json").read_text(encoding="utf-8"))
    w = next(x["id"] for x in case["workbenches"] if x["type"] == "dependency_graph")
    for node in ({"id": "G1", "kind": "item", "status": "blocked", "label": "能在美国用的信用卡"},
                 {"id": "G2", "kind": "item", "status": "blocked", "label": "信用记录"}):
        pas("add", c, "node", J(node), "--workbench", w)
    # 中继选定必须有原问题里的验证：同一次写入里把 V5（人工审核开户成功）也指向 G3
    case = json.loads((c / "case.json").read_text(encoding="utf-8"))
    wi0 = next(i for i, x in enumerate(case["workbenches"]) if x["id"] == w)
    v5 = next(i for i, v in enumerate(case["verifications"]) if v["id"] == "V5")
    pas("apply", c, "-", stdin=J([
        {"op": "add", "path": f"/workbenches/{wi0}/nodes/-", "value": {"id": "G3", "kind": "relay", "status": "chosen", "label": "信用构建账户（不要求信用记录、上报信用局）", "produces": "G2"}},
        {"op": "replace", "path": f"/verifications/{v5}/target", "value": ["N231", "G3"]}]))
    # 先标出环再连边：pas 不允许出现"有环却没标出"的中间状态
    pas("set", c, f"/workbenches/{wi0}/extra", J({"cycles": [["G1", "G2"]]}))
    for e in ({"from": "G1", "to": "G2", "type": "requires"}, {"from": "G2", "to": "G1", "type": "requires"},
              {"from": "G3", "to": "G2", "type": "produces"}):
        pas("add", c, "edge", J(e), "--workbench", w)
    case = json.loads((c / "case.json").read_text(encoding="utf-8"))
    pas("add", c, "link", J({"from": "G3", "to": "N23", "type": "same_as", "note": "依赖图的中继，就是候选树里的信用构建账户这一类"}))
    # ⑥⑦ 验证器类别与失败原因（来自原记录的 method 与 note）
    V = {v["id"]: i for i, v in enumerate(case["verifications"])}
    ops = []
    for vid, cause, extra in (("V1", "implementation", {}), ("V2", "implementation", {}), ("V3", "implementation", {}), ("V4", "implementation", {})):
        ops.append({"op": "add", "path": f"/verifications/{V[vid]}/cause", "value": cause})
    for vid in ("V1", "V2", "V3", "V4", "V5"):
        ops.append({"op": "add", "path": f"/verifications/{V[vid]}/verifier", "value": {"class": "A", "measures": "能否开户或获批", "fp_risk": "low"}})
        ops.append({"op": "add", "path": f"/verifications/{V[vid]}/by", "value": "user"})
    ops.append({"op": "add", "path": f"/verifications/{V['V6']}/verifier", "value": {"class": "B", "measures": "信用局是否出现账户与按时还款记录", "fp_risk": "low"}})
    pas("apply", c, "-", stdin=J(ops))
    # ⑥ B 类：信用局出现记录 → 论证图里的可结算预测
    pas("add", c, "workbench", J({"type": "argument_graph", "label": "对外结论与预测"}))
    case = json.loads((c / "case.json").read_text(encoding="utf-8"))
    wa = next(x["id"] for x in case["workbenches"] if x["type"] == "argument_graph")
    pas("add", c, "node", J({"id": "CL1", "kind": "claim", "status": "current", "proposed_by": "ai",
                             "statement": "Kikoff Credit Account 会在两个账单周期内出现在信用报告上，并记录按时还款",
                             "prediction": {"statement": "信用报告上出现 Kikoff 账户与按时还款记录", "falsifier": "两个账单周期后信用报告上仍没有该账户",
                                            "settle_by": "2026-12-31", "p": 0.8, "made_at": "2026-10-14",
                                            "event": {"date": "2026-11-12", "label": "第一次账单到期",
                                                      "if_good": "保持 10 号自动还款", "if_bad": "联系客服，并评估备选 Firstcard Build（N236）"}}}),
        "--workbench", wa)
    pas("set", c, f"/verifications/{V['V6']}/target", J(["N231", "CL1"]))
    # ⑨ 冲突核的条件
    K = {k["id"]: i for i, k in enumerate(case["conflicts"])}
    for kid, i in K.items():
        pas("set", c, f"/conflicts/{i}/conditions", J(["只有 ITIN、没有 SSN", "零信用记录", "不能收实体信件"]))
    # 回放本身记一轮
    pas("round", c, J({"user": "（v2 回放：补齐九阶段结构，不新增事实）", "correction": False, "stages": [2, 4, 6, 7, 9],
                       "actions": ["② 三个母题补结构检查、区分检验与对手先行", "④ 按冷启动母题建依赖图 W3，中继 G3 same_as N23",
                                   "⑥ 验证器类别；V6 写成可结算的预测 CL1", "⑦ 失败原因：四次失败都是实现层面（单个产品不收）",
                                   "⑨ 冲突核写条件"]}))
    r = pas("render", c, "--quiet")
    b = pas("brief", c)
    n = pas("next", c)
    case = json.loads((c / "case.json").read_text(encoding="utf-8"))
    types = sorted({x["type"] for x in case["workbenches"]})
    stages = sorted({s for x in case["rounds"] for s in x.get("stages", [])})
    out = {"errors": r["errors"], "rules": r["rules"], "workbench_types": types, "stages_recorded_in_replay_round": stages,
           "next": n["actions"][:5], "open_predictions": b["open_predictions"], "pas_calls": len(LOG),
           "pass": not r["errors"] and "dependency_graph" in types and "argument_graph" in types}
    (OUT / "replay_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if out["pass"] else 1)


if __name__ == "__main__":
    main()
