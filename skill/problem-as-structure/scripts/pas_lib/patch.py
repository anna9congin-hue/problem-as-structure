"""JSON Patch（RFC 6902 子集：add、replace、remove、test）。路径是 JSON Pointer。"""
import copy

from .store import PasError


def _parts(path):
    if path in ("", "/"):
        return []
    if not path.startswith("/"):
        raise PasError(f"路径必须以 / 开头：{path}", 2)
    return [p.replace("~1", "/").replace("~0", "~") for p in path[1:].split("/")]


def _walk(doc, parts, path):
    cur = doc
    for k in parts:
        try:
            cur = cur[int(k)] if isinstance(cur, list) else cur[k]
        except (KeyError, IndexError, ValueError, TypeError):
            raise PasError(f"路径不存在：{path}", 2)
    return cur


def get(doc, path):
    return _walk(doc, _parts(path), path)


def apply(doc, ops):
    if not isinstance(ops, list):
        raise PasError("补丁必须是操作列表：[{op, path, value}]", 2)
    doc = copy.deepcopy(doc)
    for op in ops:
        kind, path = op.get("op"), op.get("path", "")
        if kind not in ("add", "replace", "remove", "test"):
            raise PasError(f"不支持的操作 {kind}（只支持 add、replace、remove、test）", 2)
        parts = _parts(path)
        if not parts:
            raise PasError("不能替换整个文档", 2)
        parent = _walk(doc, parts[:-1], path)
        last = parts[-1]
        if kind == "test":
            if _walk(doc, parts, path) != op.get("value"):
                raise PasError(f"test 不成立：{path}", 1)
            continue
        if isinstance(parent, list):
            if kind == "add":
                if last == "-":
                    parent.append(op["value"])
                else:
                    parent.insert(int(last), op["value"])
            else:
                try:
                    i = int(last)
                    parent[i]
                except (ValueError, IndexError):
                    raise PasError(f"路径不存在：{path}", 2)
                if kind == "replace":
                    parent[i] = op["value"]
                else:
                    del parent[i]
        elif isinstance(parent, dict):
            if kind == "add":
                parent[last] = op["value"]
            elif last not in parent:
                raise PasError(f"路径不存在：{path}", 2)
            elif kind == "replace":
                parent[last] = op["value"]
            else:
                del parent[last]
        else:
            raise PasError(f"路径不存在：{path}", 2)
    return doc
