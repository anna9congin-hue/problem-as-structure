"""JSON Schema 子集校验器（只用标准库）。

支持：type、required、properties、additionalProperties（布尔或 schema）、enum、const、
items、$ref（本文档内 #/...）、$defs、pattern、minLength、minimum、maximum、oneOf。
其余关键字（$schema、$id、title、description 等）忽略。

validate(instance, schema) -> 错误列表，每条是 (JSON 路径, 说明)。
"""
import re

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _is_type(v, t):
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    py = _TYPES.get(t)
    return py is not None and isinstance(v, py) and not (t != "boolean" and isinstance(v, bool) and py is not bool)


def _resolve(root, ref):
    if not ref.startswith("#/"):
        raise ValueError(f"只支持本文档内的 $ref：{ref}")
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def validate(instance, schema, root=None, path="$"):
    root = root if root is not None else schema
    errs = []
    if "$ref" in schema:
        return validate(instance, _resolve(root, schema["$ref"]), root, path)
    if "oneOf" in schema:
        ok = [s for s in schema["oneOf"] if not validate(instance, s, root, path)]
        if len(ok) != 1:
            errs.append((path, f"应恰好匹配 oneOf 中的一项（匹配了 {len(ok)} 项）"))
        return errs
    t = schema.get("type")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not any(_is_type(instance, x) for x in ts):
            return [(path, f"类型应为 {t}，实际是 {type(instance).__name__}")]
    if "const" in schema and instance != schema["const"]:
        errs.append((path, f"应等于 {schema['const']!r}"))
    if "enum" in schema and instance not in schema["enum"]:
        errs.append((path, f"`{instance}` 不在 {schema['enum']}"))
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errs.append((path, f"长度至少 {schema['minLength']}"))
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errs.append((path, f"`{instance}` 不符合格式 {schema['pattern']}"))
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errs.append((path, f"不能小于 {schema['minimum']}"))
        if "maximum" in schema and instance > schema["maximum"]:
            errs.append((path, f"不能大于 {schema['maximum']}"))
    if isinstance(instance, dict):
        for k in schema.get("required", []):
            if k not in instance:
                errs.append((path, f"缺少必填字段 `{k}`"))
        props = schema.get("properties", {})
        for k, v in instance.items():
            if k in props:
                errs.extend(validate(v, props[k], root, f"{path}.{k}"))
            else:
                ap = schema.get("additionalProperties", True)
                if ap is False:
                    errs.append((path, f"不允许的字段 `{k}`"))
                elif isinstance(ap, dict):
                    errs.extend(validate(v, ap, root, f"{path}.{k}"))
    if isinstance(instance, list) and "items" in schema:
        for i, v in enumerate(instance):
            errs.extend(validate(v, schema["items"], root, f"{path}[{i}]"))
    return errs
