#!/usr/bin/env python3
"""v1 兼容入口：把 case_tool.py 的 new / check / render / html / index 转给 pas。

v2 起请直接用 scripts/pas。v1 案例先运行 `pas migrate <案例>`（会保留 case.v1.json 备份）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pas_lib.cli import main  # noqa: E402

if __name__ == "__main__":
    print("提示：case_tool.py 已由 pas 取代，参数相同的命令会直接转给 pas。", file=sys.stderr)
    main(sys.argv[1:])
