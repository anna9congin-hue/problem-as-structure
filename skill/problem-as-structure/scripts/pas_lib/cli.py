"""pas 命令行。约定：数据以 JSON 写 stdout，诊断写 stderr；不交互。

退出码：0 成功；1 校验错误（写入被拒绝，或 check/render 有 error）；2 用法错误；3 文件或 IO 错误；
4 没有 error，但有必须处理的方法规则（规则·）。
"""
import argparse
import json
import re
import shutil
import sys

from . import SCHEMA_VERSION, core_checks, patch, render, state
from .migrate import is_v2, migrate
from .store import (ASSETS, PasError, case_root, definitions, dumps, load_case, read_json,
                    resolve_case_file, today, write_atomic)

PREFIX = {"constraints": "C", "archetypes": "A", "evidence": "E", "verifications": "V", "conflicts": "K",
          "disagreements": "D", "pending": "P"}
COLLECTION = {"constraint": "constraints", "archetype": "archetypes", "evidence": "evidence", "verification": "verifications",
              "conflict": "conflicts", "disagreement": "disagreements", "pending": "pending", "link": "links",
              "workbench": "workbenches", "lesson": "retro/lessons", "stage": "stages", "running": "running"}
NODE_PREFIX = {"candidate_tree": "N", "dependency_graph": "G", "decision_tree": "T", "argument_graph": "CL", "generic_graph": "X"}


def emit(obj, code=0):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    sys.exit(code)


def read_arg_json(s):
    raw = sys.stdin.read() if s == "-" else s
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            return read_json(raw)
        except Exception:  # noqa: BLE001
            raise PasError("输入不是合法 JSON（可以直接给 JSON 字符串、文件路径，或用 - 从 stdin 读）", 2)


def _findings(res):
    return {
        "errors": [f"{f['id']}：{f['message']}" for f in res.errors],
        "rules": [f"{f['id']}：{f['message']}" + (f"（下一步：{f['action']}）" if f.get("action") else "") for f in res.rules],
        "reminds": [f"{f['id']}：{f['message']}" for f in res.all if f["level"] == "remind"],
    }


def _code(res):
    return 1 if res.errors else (4 if res.rules else 0)


def _next_id(case, prefix):
    ids = set()
    for g in ("constraints", "archetypes", "evidence", "verifications", "conflicts", "disagreements", "pending"):
        ids |= {x.get("id") for x in case.get(g, [])}
    for wb in case.get("workbenches", []):
        ids |= {n.get("id") for n in wb.get("nodes", [])}
        ids.add(wb.get("id"))
    nums = [int(m.group(1)) for i in ids if i and (m := re.fullmatch(re.escape(prefix) + r"(\d+)", i))]
    return f"{prefix}{max(nums, default=0) + 1}"


def _preview(before, after, ops):
    # 逐步应用：每条操作的前后值都相对它执行时的状态，否则数组下标移动后会显示错的对象。
    out = []
    cur = before
    for op in ops:
        path = op.get("path", "")
        nxt = patch.apply(cur, [op])
        kind = op.get("op")
        if path.endswith("/-"):
            path = path[:-2] + f"/{len(patch.get(nxt, path[:-2])) - 1}"
        b = a = None
        if kind != "add" or not path.split("/")[-1].isdigit():
            try:
                b = patch.get(cur, path)
            except PasError:
                pass
        if kind != "remove":
            try:
                a = patch.get(nxt, path)
            except PasError:
                pass
        if kind == "test":
            a = b
        out.append({"op": kind, "path": path, "before": b, "after": a})
        cur = nxt
    return out


def write_ops(case_arg, ops, dry_run=False, touch=True):
    f, case = load_case(case_arg)
    if not is_v2(case):
        raise PasError("这是 v1 案例：先运行 pas migrate", 2)
    before = core_checks.check(case)
    new = patch.apply(case, ops)
    if touch:
        new["updated"] = today()
    after = core_checks.check(new)
    old_err = {f["message"] for f in before.errors}
    introduced = [f"{x['id']}：{x['message']}" for x in after.errors if x["message"] not in old_err]
    out = {"case": str(f), "dry_run": dry_run, "preview": _preview(case, new, ops), "introduced_errors": introduced,
           **{k: v for k, v in _findings(after).items() if k != "errors"}}
    if introduced:
        out["written"] = False
        out["why"] = "写入被拒绝：这次修改会引入新的校验错误，文件没有改动"
        emit(out, 1)
    if not dry_run:
        write_atomic(f, dumps(new))
    out["written"] = not dry_run
    emit(out, 4 if after.rules and not dry_run else 0)


def cmd_new(a):
    root = case_root(a.root)
    slug = re.sub(r"[\s/\\]+", "-", a.slug.strip()).strip("-").lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise PasError("slug 只能用小写字母、数字和连字符", 2)
    d = root / f"{today()}_{slug}"
    if (d / "case.json").exists():
        raise PasError(f"案例已存在：{d}", 2)
    case = {
        "schema_version": SCHEMA_VERSION, "id": d.name, "title": a.title, "status": "open", "origin": a.origin,
        "source": {"path": "", "note": ""}, "created": today(), "updated": today(), "agent": a.agent or "", "domain": [],
        "problem": {"user_words": a.user_words or "", "goal": "", "query_type": "feasible", "initial_state": [], "success_test": ""},
        "constraints": [], "archetypes": [], "workbenches": [], "links": [], "evidence": [], "verifications": [],
        "conflicts": [], "disagreements": [], "rounds": [], "pending": [],
        "solution": {"chosen": [], "alternatives": [], "summary": ""},
        "retro": {"lessons": [], "reusable_constraints": [], "archetype_fit": "", "unmatched": []},
    }
    write_atomic(d / "case.json", dumps(case))
    emit({"created": str(d / "case.json")})


def cmd_migrate(a):
    f, case = load_case(a.case)
    if is_v2(case):
        emit({"case": str(f), "migrated": False, "why": "已经是 v2"})
    new = migrate(case, today())
    res = core_checks.check(new)
    out = {"case": str(f), "migrated": not a.dry_run, "backup": None, **_findings(res)}
    if not a.dry_run:
        bak = f.with_name("case.v1.json")
        if not bak.exists():
            shutil.copy2(f, bak)
        out["backup"] = str(bak)
        write_atomic(f, dumps(new))
    emit(out, 1 if res.errors else 0)


def _load_checked(case_arg):
    f, case = load_case(case_arg)
    if not is_v2(case):
        raise PasError(f"{f} 是 v1 案例：先运行 pas migrate（会保留 case.v1.json 备份）", 2)
    return f, case, core_checks.check(case)


def cmd_check(a):
    f, case, res = _load_checked(a.case)
    emit({"case": str(f), **_findings(res)}, _code(res))


def cmd_render(a):
    f, case, res = _load_checked(a.case)
    d = f.parent
    write_atomic(d / "tree.md", render.render_md(case, res))
    write_atomic(d / "graph.canvas", json.dumps(render.render_canvas(case), ensure_ascii=False, indent=2) + "\n")
    write_atomic(d / "progress.html", render.render_html(case, res))
    out = {"written": [str(d / x) for x in ("tree.md", "graph.canvas", "progress.html")], **_findings(res)}
    if not a.quiet:
        out["tree"] = render.tree_lines(case)
    emit(out, _code(res))


def cmd_html(a):
    f, case, res = _load_checked(a.case)
    write_atomic(f.parent / "progress.html", render.render_html(case, res))
    emit({"written": [str(f.parent / "progress.html")], "errors": _findings(res)["errors"]}, 1 if res.errors else 0)


def cmd_brief(a):
    f, case = load_case(a.case)
    emit(state.brief(case, a.limit))


def cmd_next(a):
    f, case = load_case(a.case)
    emit(state.next_actions(case))


def cmd_show(a):
    f, case = load_case(a.case)
    case = state.as_v2(case)
    for g in ("constraints", "archetypes", "evidence", "verifications", "conflicts", "disagreements", "pending"):
        for x in case.get(g, []):
            if x.get("id") == a.id:
                emit({"collection": g, "item": x})
    for wb in case.get("workbenches", []):
        if wb.get("id") == a.id:
            emit({"collection": "workbenches", "item": wb})
        for n in wb.get("nodes", []):
            if n.get("id") == a.id:
                rel = [v for v in case.get("verifications", []) if a.id in (v["target"] if isinstance(v.get("target"), list) else [v.get("target")])]
                emit({"collection": f"workbenches/{wb['id']}", "item": n, "verifications": rel})
    raise PasError(f"找不到 {a.id}", 2)


def cmd_apply(a):
    ops = read_arg_json(a.patch)
    write_ops(a.case, ops, a.dry_run)


def cmd_add(a):
    f, case = load_case(a.case)
    item = read_arg_json(a.item)
    if not isinstance(item, dict) and a.what != "lesson":
        raise PasError("要添加的内容必须是 JSON 对象", 2)
    if a.what in ("node", "edge"):
        wbs = case.get("workbenches", [])
        idx = next((i for i, w in enumerate(wbs) if w.get("id") == a.workbench), None)
        if idx is None:
            raise PasError("node / edge 需要 --workbench 指定已有的工作结构 ID", 2)
        if a.what == "node":
            if "id" not in item:
                item = {"id": _next_id(case, NODE_PREFIX.get(wbs[idx].get("type"), "X")), **item}
            path = f"/workbenches/{idx}/nodes/-"
        else:
            if "edges" not in wbs[idx]:
                write_ops(a.case, [{"op": "add", "path": f"/workbenches/{idx}/edges", "value": [item]}], a.dry_run)
            path = f"/workbenches/{idx}/edges/-"
        write_ops(a.case, [{"op": "add", "path": path, "value": item}], a.dry_run)
    coll = COLLECTION.get(a.what)
    if coll is None:
        raise PasError(f"不认识的类别 {a.what}；可用：{sorted(COLLECTION) + ['node', 'edge']}", 2)
    if a.what == "workbench":
        if "id" not in item:
            item = {"id": _next_id(case, "W"), **item}
        d = definitions().get(item.get("type"))
        if not d:
            raise PasError(f"没有工作结构类型 {item.get('type')}；可用：{sorted(definitions())}", 2)
        item.setdefault("type_version", d["version"])
        item.setdefault("nodes", [])
    elif coll in PREFIX and "id" not in item:
        item = {"id": _next_id(case, PREFIX[coll]), **item}
    if coll == "verifications":
        item.setdefault("date", today())
    ops = []
    parent = "/" + coll
    try:
        patch.get(case, parent)
    except PasError:
        ops.append({"op": "add", "path": parent, "value": []})
    ops.append({"op": "add", "path": parent + "/-", "value": item})
    write_ops(a.case, ops, a.dry_run)


def cmd_set(a):
    f, case = load_case(a.case)
    value = read_arg_json(a.value)
    try:
        patch.get(case, a.pointer)
        op = "replace"
    except PasError:
        op = "add"
    write_ops(a.case, [{"op": op, "path": a.pointer, "value": value}], a.dry_run)


def cmd_settle(a):
    f, case = load_case(a.case)
    for i, wb in enumerate(case.get("workbenches", [])):
        for j, n in enumerate(wb.get("nodes", [])):
            if n.get("id") == a.claim:
                if not n.get("prediction"):
                    raise PasError(f"{a.claim} 没有 prediction", 2)
                oc = {"date": a.date or today(), "result": a.result}
                if a.note:
                    oc["note"] = a.note
                write_ops(a.case, [{"op": "add", "path": f"/workbenches/{i}/nodes/{j}/prediction/outcome", "value": oc}], a.dry_run)
    raise PasError(f"找不到论断 {a.claim}", 2)


def cmd_round(a):
    f, case = load_case(a.case)
    r = read_arg_json(a.item)
    last = max([x.get("n", 0) for x in case.get("rounds", [])], default=0)
    r = {"n": r.get("n", last + 1), "date": r.get("date", today()), **{k: v for k, v in r.items() if k not in ("n", "date")}}
    r.setdefault("actions", [])
    r.setdefault("real_world_attempt", None)
    write_ops(a.case, [{"op": "add", "path": "/rounds/-", "value": r}], a.dry_run)


def cmd_due(a):
    emit(state.due(case_root(a.root), a.days))


def cmd_search(a):
    emit(state.search(case_root(a.root), a.query))


def cmd_index(a):
    root = case_root(a.root)
    text, n = state.index_md(root)
    root.mkdir(parents=True, exist_ok=True)
    write_atomic(root / "INDEX.md", text)
    emit({"written": str(root / "INDEX.md"), "cases": n})


def cmd_self_check(a):
    from .jsonschema_lite import validate
    meta = read_json(ASSETS / "workbench.meta.schema.json")
    probs = []
    for k, d in definitions().items():
        probs += [f"{k}{p[1:]}：{m}" for p, m in validate(d, meta)]
    ok = sys.version_info >= (3, 8) and not probs
    emit({"python": sys.version.split()[0], "schema_version": SCHEMA_VERSION, "workbench_types": sorted(definitions()),
          "assets": str(ASSETS), "problems": probs, "ok": ok}, 0 if ok else 1)


def cmd_schema(a):
    defs = definitions()
    emit({"case_schema": str(ASSETS / "case.v2.schema.json"),
          "workbench_types": {k: {"label": d["label"], "version": d["version"], "node_kinds": sorted(d["node_types"]),
                                  "statuses": sorted(d["statuses"]), "edge_types": sorted(d["edge_types"]),
                                  "used_by_archetypes": d.get("used_by_archetypes", [])} for k, d in defs.items()}})


def build_parser():
    ap = argparse.ArgumentParser(prog="pas", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def sp(name, fn, help_, case=True):
        p = sub.add_parser(name, help=help_, description=help_)
        if case:
            p.add_argument("case", help="案例目录或 case.json")
        p.set_defaults(func=fn)
        return p

    p = sp("new", cmd_new, "新建 v2 案例", case=False)
    p.add_argument("--slug", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--origin", default="live", choices=["live", "retro"])
    p.add_argument("--agent")
    p.add_argument("--user-words")
    p.add_argument("--root")
    p = sp("migrate", cmd_migrate, "把 v1 案例无损升级到 v2（保留 case.v1.json 备份）")
    p.add_argument("--dry-run", action="store_true")
    sp("check", cmd_check, "只校验")
    p = sp("render", cmd_render, "校验并生成 tree.md、graph.canvas、progress.html")
    p.add_argument("--quiet", action="store_true", help="不在输出里附状态树")
    sp("html", cmd_html, "只生成 progress.html")
    p = sp("brief", cmd_brief, "当前状态（每轮开始只读这个）")
    p.add_argument("--limit", type=int, default=6000, help="输出字符上限")
    sp("next", cmd_next, "按状态给出可做的下一步")
    p = sp("show", cmd_show, "看单个对象")
    p.add_argument("id")
    p = sp("apply", cmd_apply, "批量修改（JSON Patch）；会引入新错误的修改被拒绝")
    p.add_argument("patch", help="补丁 JSON、文件路径，或 - 从 stdin 读")
    p.add_argument("--dry-run", action="store_true", help="只预览差异，不写入（用于给用户的提案）")
    p = sp("add", cmd_add, "添加一个对象；没写 id 时自动编号")
    p.add_argument("what", help="constraint、archetype、evidence、verification、conflict、disagreement、pending、link、workbench、lesson、stage、running、node、edge")
    p.add_argument("item", help="JSON、文件路径，或 -")
    p.add_argument("--workbench", help="node / edge 所属的工作结构 ID")
    p.add_argument("--dry-run", action="store_true")
    p = sp("set", cmd_set, "设置一个字段（JSON Pointer）")
    p.add_argument("pointer")
    p.add_argument("value", help="JSON、文件路径，或 -")
    p.add_argument("--dry-run", action="store_true")
    p = sp("settle", cmd_settle, "结算一条预测")
    p.add_argument("claim")
    p.add_argument("result", choices=["true", "false", "void"])
    p.add_argument("--note")
    p.add_argument("--date")
    p.add_argument("--dry-run", action="store_true")
    p = sp("round", cmd_round, "追加一轮记录（n 和日期自动补）")
    p.add_argument("item", help="JSON、文件路径，或 -")
    p.add_argument("--dry-run", action="store_true")
    p = sp("due", cmd_due, "列出到期待结算的预测（跨案例）", case=False)
    p.add_argument("--root")
    p.add_argument("--days", type=int, default=0, help="往后看几天")
    p = sp("search", cmd_search, "跨案例检索冲突核、经验、可复用约束、出局原因、母题", case=False)
    p.add_argument("query")
    p.add_argument("--root")
    p = sp("index", cmd_index, "重建案例库 INDEX.md", case=False)
    p.add_argument("--root")
    sp("self-check", cmd_self_check, "检查环境、定义文件", case=False)
    sp("schema", cmd_schema, "列出 schema 路径与工作结构类型", case=False)
    return ap


def main(argv=None):
    ap = build_parser()
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        if e.code not in (0, None):
            sys.exit(2)
        raise
    try:
        a.func(a)
    except PasError as e:
        print(f"错误：{e}", file=sys.stderr)
        emit({"error": str(e)}, e.code)
    except FileNotFoundError as e:
        print(f"错误：{e}", file=sys.stderr)
        emit({"error": str(e)}, 3)
