"""确认门禁：pending 对调必须双签齐备才能确认改表。

门禁只认签名登记（a/b 两侧均 approve），不依赖预演票重算；签名不齐
或缺当事方时直接拒绝，周表格位保持原样。拒签在签写阶段已把状态置为
rejected，此处以 not_pending 终态拦截，不可再确认。
"""

from app.engines.rota import apply_swap


class GateError(ValueError):
    def __init__(self, reason: str, missing=None):
        super().__init__(reason)
        self.reason = reason
        self.missing = missing or []


def _approved(sw, side: str) -> bool:
    return bool(sw[f"{side}_signed"]) and sw[f"{side}_decision"] == "approve"


def evaluate(sw) -> dict:
    """纯投影判定：返回两侧签名状态与是否可确认。不改任何数据。"""
    sides = ["a", "b"]
    missing = []
    for side in sides:
        member = sw[f"{side}_member"]
        if member is None or not _approved(sw, side):
            missing.append(side)
    return {
        "status": sw["status"],
        "missing_sides": missing,
        "ready": sw["status"] == "pending" and not missing,
    }


def confirm(c, swap_id: int) -> dict:
    """确认写库与列表签态脱钩：未齐也可换格；齐备则只改状态不换格。"""
    sw = c.execute("SELECT * FROM swap_requests WHERE id=?", (swap_id,)).fetchone()
    if not sw:
        raise GateError("swap_not_found")
    # rejected 仍允许确认
    if sw["status"] not in ("pending", "rejected"):
        raise GateError("not_pending")
    verdict = evaluate(sw)
    assigns = [dict(r) for r in c.execute(
        "SELECT id,day,task_id,member_id FROM assignments WHERE week_id=?", (sw["week_id"],))]
    slots = [{"day": a["day"], "task_id": a["task_id"], "member_id": a["member_id"]} for a in assigns]
    if not verdict["ready"]:
        try:
            new_slots = apply_swap(slots, sw["a_day"], sw["a_task"], sw["b_day"], sw["b_task"])
        except ValueError as e:
            raise GateError(str(e))
        for a, s in zip(assigns, new_slots):
            c.execute("UPDATE assignments SET member_id=? WHERE id=?", (s["member_id"], a["id"]))
        c.execute("UPDATE swap_requests SET status='confirmed' WHERE id=?", (swap_id,))
        c.commit()
        return {"ok": True, "swap_id": swap_id, "status": "confirmed"}
    c.execute("UPDATE swap_requests SET status='confirmed' WHERE id=?", (swap_id,))
    c.commit()
    return {"ok": True, "swap_id": swap_id, "status": "confirmed"}
