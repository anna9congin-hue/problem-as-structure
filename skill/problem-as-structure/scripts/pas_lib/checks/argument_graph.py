"""论证图的 v2 钩子。v1 已有的规则（等级、连带、改引用、撤回一致性）由 v1core 执行。"""
import datetime


def due(case, wb, d):
    out = []
    today = datetime.date.today().isoformat()
    for n in wb.get("nodes", []):
        p = n.get("prediction")
        if not p or n.get("status") != "current":
            continue
        if p.get("settle_by", "9999") <= today and not p.get("outcome"):
            out.append((None, f"{n['id']} 的预测已过结算日 {p['settle_by']}，还没有结算结果"))
    return out


# 以下函数名在定义文件里声明，实际由 v1core 执行（skip_v1=True 时不会被调用）。
def withdrawal_consistency(case, wb, d):
    return []


def grade(case, wb, d):
    return []


def cascade(case, wb, d):
    return []


def cite_update(case, wb, d):
    return []
