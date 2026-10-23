"""读写案例与定义文件。写入一律原子：先写临时文件，再 os.replace。"""
import datetime
import json
import os
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS = SKILL_DIR / "assets"
DEFAULT_ROOT = (
    "/Users/leiyuan/Library/Mobile Documents/iCloud~md~obsidian/Documents/"
    "freedom/investment_method/problem_cases"
)


class PasError(Exception):
    """带退出码的错误：2 用法错误，3 文件或 IO 错误。"""

    def __init__(self, msg, code=3):
        super().__init__(msg)
        self.code = code


def today():
    return datetime.date.today().isoformat()


def case_root(arg_root=None):
    return Path(arg_root or os.environ.get("PROBLEM_CASES_DIR") or DEFAULT_ROOT)


def resolve_case_file(p):
    p = Path(p)
    if p.is_dir():
        p = p / "case.json"
    if not p.exists():
        raise PasError(f"找不到案例文件：{p}", 3)
    return p


def read_json(path):
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PasError(f"{path} 不是合法 JSON：第 {e.lineno} 行第 {e.colno} 列：{e.msg}", 3)


def load_case(p):
    f = resolve_case_file(p)
    return f, read_json(f)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def write_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pas-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


_DEFS = None


def definitions():
    """工作结构定义：{type_id: definition}。"""
    global _DEFS
    if _DEFS is None:
        _DEFS = {}
        for f in sorted((ASSETS / "workbenches").glob("*.json")):
            d = read_json(f)
            _DEFS[d["id"]] = d
    return _DEFS


_SCHEMA = None


def core_schema():
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = read_json(ASSETS / "case.v2.schema.json")
    return _SCHEMA
