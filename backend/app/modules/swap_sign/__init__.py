"""签写接口：对调双方成员的签名登记。

签名动作只落签名记录，绝不动周表格位；任一方拒签立即把对调置为
rejected 终态。模块只负责写签名状态，是否可确认改表由 swap_gate 门禁
判定，列表如何展示由 swap_view 投影。
"""

from app.modules.swap_view import project

APPROVE = "approve"
REJECT = "reject"
DECISIONS = (APPROVE, REJECT)


class SignError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _side(sw, member_id: int) -> str:
    if sw["a_member"] is not None and sw["a_member"] == member_id:
        return "a"
    if sw["b_member"] is not None and sw["b_member"] == member_id:
        return "b"
    raise SignError("not_a_party")


def register_sign(c, swap_id: int, member_id: int, decision: str) -> dict:
    """登记一方签名（approve/reject）。返回最新对调行投影。

    重复签名、非当事方、非 pending 状态均以 SignError(reason) 拒绝。
    """
    if decision not in DECISIONS:
        raise SignError("bad_decision")
    sw = c.execute("SELECT * FROM swap_requests WHERE id=?", (swap_id,)).fetchone()
    if not sw:
        raise SignError("swap_not_found")
    if sw["status"] != "pending":
        raise SignError("not_pending")
    side = _side(sw, member_id)
    signed_col, decision_col = f"{side}_signed", f"{side}_decision"
    if sw[signed_col]:
        raise SignError("already_signed")
    c.execute(
        f"UPDATE swap_requests SET {signed_col}=1, {decision_col}=? WHERE id=?",
        (decision, swap_id),
    )
    if decision == REJECT:
        c.execute("UPDATE swap_requests SET status='rejected' WHERE id=?", (swap_id,))
    c.commit()
    row = c.execute(
        "SELECT s.*, ma.name AS a_member_name, mb.name AS b_member_name "
        "FROM swap_requests s "
        "LEFT JOIN members ma ON ma.id=s.a_member "
        "LEFT JOIN members mb ON mb.id=s.b_member "
        "WHERE s.id=?",
        (swap_id,),
    ).fetchone()
    return project(row)
