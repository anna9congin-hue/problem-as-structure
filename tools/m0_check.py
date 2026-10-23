#!/usr/bin/env python3
"""M0 验收：在写任何实现之前，确认 schema、定义文件、夹具、坏数据测试本身是对的。

检查项（全部通过才算 M0 完成）：
  1. 所有 JSON 文件能解析。
  2. 每个工作结构定义符合 workbench.meta.schema.json；rule/remind 级不变量都写了 action。
  3. 干净样本 base_clean.v2.json 符合 case.v2.schema.json。
  4. 每条坏数据测试的 ops 都能应用到干净样本上（路径有效）。
  5. 期望 SCHEMA 的坏数据测试，改坏后确实不符合 schema；其余的改坏后仍然符合 schema
     （说明它们测的是不变量，而不是格式）——这是"干净双生"在格式层的检验。
  6. 坏数据测试期望的每个不变量 ID，都在 docs/invariants.md 或某个定义文件里有定义。
  7. 夹具的 SHA-256 与 MANIFEST.json 一致（快照没被改动）。

用法：python3 tools/m0_check.py      输出 JSON 摘要到 stdout；失败时退出码 1。
"""
import copy
import glob
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "problem-as-structure"
sys.path.insert(0, str(SKILL / "scripts"))
from pas_lib.jsonschema_lite import validate  # noqa: E402


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def pointer_parts(path):
    return [p.replace("~1", "/").replace("~0", "~") for p in path.lstrip("/").split("/")] if path else []


def apply_ops(doc, ops):
    doc = copy.deepcopy(doc)
    for op in ops:
        parts = pointer_parts(op["path"])
        parent = doc
        for k in parts[:-1]:
            parent = parent[int(k)] if isinstance(parent, list) else parent[k]
        last = parts[-1]
        if isinstance(parent, list):
            if op["op"] == "add":
                parent.append(op["value"]) if last == "-" else parent.insert(int(last), op["value"])
            elif op["op"] == "replace":
                parent[int(last)] = op["value"]
            elif op["op"] == "remove":
                del parent[int(last)]
        else:
            if op["op"] in ("add", "replace"):
                if op["op"] == "replace" and last not in parent:
                    raise KeyError(f"replace 的路径不存在：{op['path']}")
                parent[last] = op["value"]
            elif op["op"] == "remove":
                if last not in parent:
                    raise KeyError(f"remove 的路径不存在：{op['path']}")
                del parent[last]
    return doc


def main():
    fails = []
    F = fails.append
    # 1
    files = [f for f in glob.glob(str(ROOT / "**" / "*.json"), recursive=True)]
    for f in files:
        try:
            load(f)
        except Exception as e:  # noqa: BLE001
            F(f"JSON 解析失败：{f}：{e}")
    core = load(SKILL / "assets" / "case.v2.schema.json")
    meta = load(SKILL / "assets" / "workbench.meta.schema.json")
    # 2
    defs = {}
    for f in sorted(glob.glob(str(SKILL / "assets" / "workbenches" / "*.json"))):
        d = load(f)
        defs[d["id"]] = d
        for path, msg in validate(d, meta):
            F(f"定义 {Path(f).name} {path}：{msg}")
        if Path(f).stem != d["id"]:
            F(f"定义文件名 {Path(f).name} 与 id {d['id']} 不一致")
        for inv in d["invariants"]:
            if inv["level"] in ("rule", "remind") and not inv.get("action"):
                F(f"定义 {d['id']} 的不变量 {inv['id']} 是 {inv['level']} 级，但没写 action")
    # 3
    base = load(ROOT / "tests" / "poison" / "base_clean.v2.json")
    for path, msg in validate(base, core):
        F(f"干净样本不符合 schema：{path}：{msg}")
    for wb in base["workbenches"]:
        if wb["type"] not in defs:
            F(f"干净样本的工作结构 {wb['id']} 类型 {wb['type']} 没有定义文件")
    # 6 准备：已定义的不变量 ID
    inv_doc = (ROOT / "docs" / "invariants.md").read_text(encoding="utf-8")
    known = set(re.findall(r"\b[A-Z]{2}-\d{2}\b", inv_doc)) | {"SCHEMA"}
    for d in defs.values():
        known |= {i["id"] for i in d["invariants"]}
    # 4、5、6
    spec = load(ROOT / "tests" / "poison" / "poisons.json")
    results = []
    for t in spec["tests"]:
        try:
            bad = apply_ops(base, t["ops"])
        except Exception as e:  # noqa: BLE001
            F(f"{t['id']} 的 ops 无法应用：{e}")
            continue
        schema_errs = validate(bad, core)
        wants_schema = "SCHEMA" in t["expect"]
        if wants_schema and not schema_errs:
            F(f"{t['id']} 期望 schema 报错，但改坏后仍符合 schema")
        if not wants_schema and schema_errs:
            F(f"{t['id']} 应该测不变量，但改坏后先违反了 schema：{schema_errs[:2]}")
        for x in t["expect"]:
            if x not in known:
                F(f"{t['id']} 期望的不变量 {x} 没有定义")
        results.append(t["id"])
    # 7
    mf = ROOT / "tests" / "fixtures" / "MANIFEST.json"
    if mf.exists():
        man = load(mf)
    else:
        print("跳过夹具校验：tests/fixtures 不存在（公开仓库不含真实案例）", file=sys.stderr)
        man = {"fixtures": {}}
    v1 = ROOT / "tests" / "v1_reference" / "case_tool.py"
    if "v1_tool_sha256" in man and hashlib.sha256(v1.read_bytes()).hexdigest() != man["v1_tool_sha256"]:
        F("冻结的 v1 工具被改动了")
    for name, m in man["fixtures"].items():
        d = ROOT / "tests" / "fixtures" / name
        if hashlib.sha256((d / "case.json").read_bytes()).hexdigest() != m["case_sha256"]:
            F(f"夹具 {name} 的 case.json 被改动了")
        for fn, h in m["outputs"].items():
            if hashlib.sha256((d / "v1" / fn).read_bytes()).hexdigest() != h:
                F(f"夹具 {name} 的 v1 输出 {fn} 被改动了")
    summary = {
        "definitions": sorted(defs),
        "poison_tests": len(results),
        "poison_schema": sum(1 for t in spec["tests"] if "SCHEMA" in t["expect"]),
        "fixtures": sorted(man["fixtures"]),
        "failures": fails,
        "pass": not fails,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
