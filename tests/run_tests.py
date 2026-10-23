#!/usr/bin/env python3
"""v2 的全部自动测试（只用标准库）。

  1. 差分测试：3 个真实案例 migrate 后，
     a) v1 视图与原 v1 案例语义相同（论断补了 status=current 除外）；
     b) v1 规则的错误与提醒逐字一致；
     c) tree.md 去掉 v2 小节与 v2 发现后，与 v1 输出逐字一致；
     d) graph.canvas 逐字一致；
     e) progress.html 去掉时间戳、内嵌数据和 v2 区块后逐字一致，内嵌数据语义一致。
  2. 坏数据测试：每条都报出期望的不变量 ID；干净样本没有 error。
  3. 写入测试：pas apply 拒绝会引入新错误的修改；随机写入序列之后文件始终通过校验。
  4. 命令测试：pas 的每个子命令在干净样本上能运行，stdout 是合法 JSON。

用法：python3 tests/run_tests.py     结果 JSON 写 stdout；有失败时退出码 1。
"""
import copy
import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "problem-as-structure"
PAS = SKILL / "scripts" / "pas"
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))
from pas_lib import core_checks, migrate, render  # noqa: E402
from m0_check import apply_ops  # noqa: E402

TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
V2_LINE = re.compile(r"^- (错误|提醒)：[A-Z]{2,6}-\d{2}：|^- (错误|提醒)：SCHEMA：")
FAILS = []


def fail(msg):
    FAILS.append(msg)


def strip_v2_md(text):
    out, skip = [], False
    for line in text.split("\n"):
        if line.startswith("## "):
            skip = any(line.startswith(h) for h in render.V2_SECTIONS)
        if skip:
            continue
        if V2_LINE.search(line):
            continue
        out.append(line)
    s = "\n".join(out)
    # v1 没有任何发现时写"全部通过。"；v2 有发现而 v1 没有时，补回这一行再比较
    if "## 校验\n\n" in s and s.rstrip().endswith("## 校验"):
        s = s.rstrip() + "\n\n全部通过。\n"
    return s


def norm_claims(case):
    c = copy.deepcopy(case)
    for x in c.get("claims", []):
        x.setdefault("status", "current")
    return c


def html_parts(page):
    page = TS.sub("0000-00-00T00:00:00", page)
    page = re.sub(re.escape(render.HTML_BEGIN) + ".*?" + re.escape(render.HTML_END), "", page, flags=re.S)
    m = re.search(r'<script type="application/json" id="case-data">(.*?)</script>', page, re.S)
    data = None
    if m:
        data = json.loads(m.group(1).replace("<\\/", "</"))
        page = page[:m.start(1)] + "@@DATA@@" + page[m.end(1):]
    return page, data


def differential():
    fx = ROOT / "tests" / "fixtures"
    if not fx.is_dir():
        print("跳过差分测试：tests/fixtures 不存在（公开仓库不含真实案例）", file=sys.stderr)
        return
    for d in sorted(fx.iterdir()):
        if not d.is_dir():
            continue
        name = d.name
        v1 = json.loads((d / "case.json").read_text(encoding="utf-8"))
        v2 = migrate.migrate(v1, "2026-10-22")
        view = render.clean_view(v2)
        if json.dumps(norm_claims(view), sort_keys=True, ensure_ascii=False) != json.dumps(norm_claims(v1), sort_keys=True, ensure_ascii=False):
            a, b = norm_claims(view), norm_claims(v1)
            diff = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
            fail(f"{name}: v1 视图与原案例不一致，字段 {diff}")
        res = core_checks.check(v2)
        from pas_lib import v1core
        e1, w1 = v1core.check(v1)
        if res.v1_errors != e1 or res.v1_warnings != w1:
            fail(f"{name}: v1 规则输出不一致（v2 {len(res.v1_errors)}/{len(res.v1_warnings)}，v1 {len(e1)}/{len(w1)}）")
        bad = [f for f in res.findings if f["level"] == "error"]
        if bad:
            fail(f"{name}: 迁移后出现 v2 error：{bad[:3]}")
        md = render.render_md(v2, res)
        want = (d / "v1" / "tree.md").read_text(encoding="utf-8")
        got = strip_v2_md(md)
        if got != want:
            gl, wl = got.split("\n"), want.split("\n")
            k = next((i for i, (x, y) in enumerate(zip(gl, wl)) if x != y), min(len(gl), len(wl)))
            fail(f"{name}: tree.md 第 {k + 1} 行不同：v2「{gl[k] if k < len(gl) else '<EOF>'}」 v1「{wl[k] if k < len(wl) else '<EOF>'}」")
        cv = json.dumps(render.render_canvas(v2), ensure_ascii=False, indent=2) + "\n"
        if cv != (d / "v1" / "graph.canvas").read_text(encoding="utf-8"):
            fail(f"{name}: graph.canvas 不同")
        p2, d2 = html_parts(render.render_html(v2, res))
        p1, d1 = html_parts((d / "v1" / "progress.html").read_text(encoding="utf-8"))
        if p2 != p1:
            fail(f"{name}: progress.html 页面部分不同")
        if d1 is not None and d2 is not None:
            for k in ("case",):
                pass
            if json.dumps(_strip_payload(d2), sort_keys=True) != json.dumps(_strip_payload(d1), sort_keys=True):
                fail(f"{name}: progress.html 内嵌数据不同")
        yield name


def _strip_payload(d):
    d = copy.deepcopy(d)
    case = d.get("case") or {}
    for x in case.get("claims", []):
        x.setdefault("status", "current")
    # v2 的校验发现会出现在内嵌的 errors / warnings 里；只比较 v1 的部分
    for k in ("errors", "warnings"):
        if isinstance(d.get(k), list):
            d[k] = [m for m in d[k] if not re.match(r"^[A-Z]{2,6}-\d{2}：|^SCHEMA：", m)]
    return d


def poison():
    base = json.loads((ROOT / "tests" / "poison" / "base_clean.v2.json").read_text(encoding="utf-8"))
    r0 = core_checks.check(base)
    errs = r0.errors
    if errs:
        fail(f"干净样本有 error：{errs[:3]}")
    spec = json.loads((ROOT / "tests" / "poison" / "poisons.json").read_text(encoding="utf-8"))
    n = 0
    for t in spec["tests"]:
        bad = apply_ops(base, t["ops"])
        r = core_checks.check(bad)
        ids = {f["id"] for f in r.all}
        miss = [x for x in t["expect"] if x not in ids]
        if miss:
            fail(f"{t['id']}（{t['about']}）没有报出 {miss}；实际：{sorted(ids - {f['id'] for f in r0.all})}")
        n += 1
    return n, len(r0.all)


def pas(*args, stdin=None):
    p = subprocess.run([sys.executable, str(PAS)] + [str(a) for a in args], capture_output=True, text=True, input=stdin)
    return p.returncode, p.stdout, p.stderr


def commands():
    tmp = Path(tempfile.mkdtemp(prefix="pas-test-"))
    case_dir = tmp / "2026-10-14_itin-mini"
    case_dir.mkdir()
    base = json.loads((ROOT / "tests" / "poison" / "base_clean.v2.json").read_text(encoding="utf-8"))
    (case_dir / "case.json").write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    ran = []
    for args in (["check", case_dir], ["render", case_dir], ["html", case_dir], ["brief", case_dir], ["next", case_dir],
                 ["show", case_dir, "N21"], ["due", "--root", tmp], ["search", "零信用", "--root", tmp], ["index", "--root", tmp],
                 ["self-check"], ["schema"]):
        code, out, err = pas(*args)
        try:
            json.loads(out)
        except json.JSONDecodeError:
            fail(f"pas {args[0]} 的 stdout 不是 JSON（退出码 {code}）：{out[:120]} {err[:200]}")
        if code not in (0, 4):
            fail(f"pas {args[0]} 退出码 {code}：{err[:200]}")
        ran.append(args[0])
    # 写入：合法修改应通过，引入错误的修改应被拒绝且文件不变
    before = (case_dir / "case.json").read_text(encoding="utf-8")
    good = json.dumps([{"op": "add", "path": "/constraints/-", "value": {"id": "C9", "text": "测试约束", "kind": "soft", "basis": "value", "verified": True}}])
    code, out, err = pas("apply", case_dir, "-", stdin=good)
    if code != 0:
        fail(f"合法的 apply 被拒绝：{out[:200]} {err[:200]}")
    mid = (case_dir / "case.json").read_text(encoding="utf-8")
    badp = json.dumps([{"op": "replace", "path": "/workbenches/0/nodes/6/status", "value": "pruned"},
                       {"op": "add", "path": "/workbenches/0/nodes/6/pruned_by", "value": ["C4"]}])
    code, out, err = pas("apply", case_dir, "-", stdin=badp)
    if code != 1:
        fail(f"软偏好淘汰的 apply 没有被拒绝（退出码 {code}）")
    if (case_dir / "case.json").read_text(encoding="utf-8") != mid:
        fail("被拒绝的 apply 改动了文件")
    code, out, err = pas("apply", case_dir, "-", "--dry-run", stdin=good.replace("C9", "C10"))
    if (case_dir / "case.json").read_text(encoding="utf-8") != mid or code != 0:
        fail("dry-run 改动了文件或失败")
    if before == mid:
        fail("合法的 apply 没有写入")
    # add / set / settle / round
    for args, stdin in (
        (["add", case_dir, "evidence", "-"], json.dumps({"claim": "测试证据", "type": "fact", "source": "测试", "verified": True})),
        (["add", case_dir, "node", "-", "--workbench", "W2"], json.dumps({"kind": "action", "status": "open", "label": "测试动作"})),
        (["set", case_dir, "/workbenches/1/nodes/0/note", "-"], json.dumps("测试备注")),
        (["settle", case_dir, "CL1", "true", "--note", "测试结算"], None),
        (["round", case_dir, "-"], json.dumps({"user": "测试", "stages": [9], "actions": ["测试写入"]})),
    ):
        code, out, err = pas(*args, stdin=stdin)
        if code != 0:
            fail(f"pas {' '.join(map(str, args[:3]))} 失败：{out[:200]} {err[:200]}")
        ran.append(args[0])
    # 随机写入序列：每次之后文件都通过校验（不出现新 error）
    rng = random.Random(7)
    for i in range(40):
        c = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        ops = rng.choice([
            [{"op": "replace", "path": "/workbenches/0/nodes/6/status", "value": rng.choice(["pruned", "open", "parked", "chosen", "failed"])}],
            [{"op": "add", "path": "/verifications/-", "value": {"id": f"VR{i}", "target": "N22", "method": "随机", "result": rng.choice(["fail", "pass", "pending"])}}],
            [{"op": "replace", "path": "/evidence/0/observed_at", "value": rng.choice(["2026-10-01", "2026-10-30"])}],
            [{"op": "remove", "path": "/archetypes/1/structural_checks"}] if c["archetypes"][1].get("structural_checks") else [{"op": "add", "path": "/archetypes/1/structural_checks", "value": ["约束能列清楚"]}],
            [{"op": "add", "path": "/workbenches/1/edges/-", "value": {"from": "G3", "to": rng.choice(["G1", "G2"]), "type": rng.choice(["requires", "produces"])}}],
        ])
        pas("apply", case_dir, "-", stdin=json.dumps(ops))
        after = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        if core_checks.check(after).errors:
            fail(f"随机写入第 {i} 步之后文件有 error：{core_checks.check(after).errors[:2]}")
            break
    return ran


def main():
    names = list(differential())
    n_poison, base_findings = poison()
    ran = commands()
    out = {"differential": names, "poison_tests": n_poison, "clean_base_findings": base_findings, "commands": ran,
           "failures": FAILS, "pass": not FAILS}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    main()
