#!/usr/bin/env python3
"""冻结 v1 的输出，作为 v2 差分测试的参照（M0）。

做法：把真实案例的 case.json 快照复制到 tests/fixtures/<case>/case.json，
用冻结的 v1 工具（tests/v1_reference/case_tool.py）跑 check 与 render，
把 tree.md、graph.canvas、progress.html 和 check 的输出存到 tests/fixtures/<case>/v1/。

progress.html 里嵌了生成时间，存档时把它替换成固定占位符，比较时 v2 也做同样处理。

用法：python3 tools/freeze_v1.py [--force]
只用 Python 标准库。
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "tests" / "v1_reference" / "case_tool.py"
FIX = ROOT / "tests" / "fixtures"
PAPER = Path(
    "/Users/leiyuan/Library/Mobile Documents/iCloud~md~obsidian/Documents/"
    "freedom/investment_method/paper_problem_as_structure"
)
SOURCES = {
    "itin-credit-builder": PAPER / "cases" / "2026-10-14_itin-credit-builder" / "case.json",
    "paper-problem-as-structure": PAPER / "cases" / "2026-10-17_paper-problem-as-structure" / "case.json",
    "s4-gap-supplement-b": PAPER / "reports" / "S4_增补" / "B" / "2026-10-21_s4-gap-supplement" / "case.json",
}
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
PLACEHOLDER = "0000-00-00T00:00:00"


def normalize_html(text: str) -> str:
    return TIMESTAMP.sub(PLACEHOLDER, text)


def run(args, cwd):
    p = subprocess.run([sys.executable, str(V1)] + args, cwd=cwd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="覆盖已有的快照（默认已存在就停）")
    a = ap.parse_args()
    manifest = {"v1_tool_sha256": sha(V1), "fixtures": {}}
    for name, src in SOURCES.items():
        d = FIX / name
        if d.exists() and not a.force:
            sys.exit(f"{d} 已存在；要重新冻结请加 --force")
        if d.exists():
            shutil.rmtree(d)
        (d / "v1").mkdir(parents=True)
        shutil.copy2(src, d / "case.json")
        work = d / "v1"
        shutil.copy2(d / "case.json", work / "case.json")
        code, out, err = run(["check", str(work)], cwd=ROOT)
        (work / "check.stdout.txt").write_text(out, encoding="utf-8")
        (work / "check.stderr.txt").write_text(err, encoding="utf-8")
        code_r, out_r, err_r = run(["render", str(work)], cwd=ROOT)
        (work / "render.stdout.txt").write_text(out_r, encoding="utf-8")
        html = work / "progress.html"
        html.write_text(normalize_html(html.read_text(encoding="utf-8")), encoding="utf-8")
        (work / "case.json").unlink()
        manifest["fixtures"][name] = {
            "source": str(src),
            "case_sha256": sha(d / "case.json"),
            "check_exit": code,
            "render_exit": code_r,
            "outputs": {f.name: sha(f) for f in sorted(work.iterdir())},
        }
        print(f"{name}: check={code} render={code_r}", file=sys.stderr)
    (FIX / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"frozen": list(SOURCES)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
