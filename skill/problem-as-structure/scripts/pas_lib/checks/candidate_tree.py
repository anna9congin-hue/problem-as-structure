"""候选树的钩子。CT-13 到 CT-17 都是 v1 规则，由 v1core 执行，逐字保持 v1 的消息。

候选树不是主工作结构时（一个案例里第二棵候选树），这些钩子才会被调用；
此时把它投影成 v1 视图，借用 v1core 的同一段代码，只取对应的提醒。
"""
import copy

from .. import v1core

_TAGS = {
    "park_reference": ("规则·参照失效", "规则·可行集最优", "park_reference"),
    "sibling_contrast": ("规则·对照",),
    "jump_back": ("规则·跳级回溯",),
    "reexamine_parked": ("规则·重审搁置",),
    "prune_without_fact": ("被淘汰但没附事实依据",),
}


def _run(case, wb, tags):
    view = copy.deepcopy(case)
    view["schema_version"] = 1
    view["nodes"] = copy.deepcopy(wb["nodes"])
    view.pop("workbenches", None)
    view.pop("claims", None)
    view["archetypes"] = [dict(a, status="active" if a.get("status") == "accepted" else a.get("status")) for a in view.get("archetypes", [])]
    view["verifications"] = [v for v in view.get("verifications", []) if not isinstance(v.get("target"), list)]
    errs, warns = v1core.check(view)
    return [(None, w) for w in warns if any(t in w for t in tags)]


def park_reference(case, wb, d):
    return _run(case, wb, _TAGS["park_reference"])


def sibling_contrast(case, wb, d):
    return _run(case, wb, _TAGS["sibling_contrast"])


def jump_back(case, wb, d):
    return _run(case, wb, _TAGS["jump_back"])


def reexamine_parked(case, wb, d):
    return _run(case, wb, _TAGS["reexamine_parked"])


def prune_without_fact(case, wb, d):
    return _run(case, wb, _TAGS["prune_without_fact"])
