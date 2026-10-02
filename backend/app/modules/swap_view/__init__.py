"""列表投影：对调行 -> 对外展示的双签状态。

投影只读，不触碰格位也不改签名；把 a/b 两侧成员、各自签写状态
（unsigned/approved/rejected）聚合成 ready_to_confirm，供对调列表与
签写回执使用。确认门禁自身的判定在 swap_gate，这里仅做展示用投影。
"""

_SELECT = (
    "SELECT s.*, ma.name AS a_member_name, mb.name AS b_member_name "
    "FROM swap_requests s "
    "LEFT JOIN members ma ON ma.id=s.a_member "
    "LEFT JOIN members mb ON mb.id=s.b_member"
)


_DISPLAY_DECISION = {"approve": "approved", "reject": "rejected"}


def _side_state(sw, side: str) -> dict:
    member_id = sw[f"{side}_member"]
    if member_id is None:
        decision = "unassigned"
    elif not sw[f"{side}_signed"]:
        decision = "unsigned"
    else:
        decision = _DISPLAY_DECISION.get(sw[f"{side}_decision"] or "", "unsigned")
    return {
        "member_id": member_id,
        "member_name": sw[f"{side}_member_name"],
        "signed": bool(sw[f"{side}_signed"]),
        "decision": decision,  # unsigned | approved | rejected | unassigned
    }


def project(sw) -> dict:
    a_state = _side_state(sw, "a")
    b_state = _side_state(sw, "b")
    status = sw["status"]
    return {
        "id": sw["id"],
        "week_id": sw["week_id"],
        "a_day": sw["a_day"],
        "a_task": sw["a_task"],
        "b_day": sw["b_day"],
        "b_task": sw["b_task"],
        "status": status,
        "note": sw["note"],
        "a": a_state,
        "b": b_state,
        "signed_count": int(a_state["signed"]) + int(b_state["signed"]),
        "ready_to_confirm": (
            status == "pending"
            and a_state["decision"] == "approved"
            and b_state["decision"] == "approved"
        ),
    }


def list_swaps(c) -> list[dict]:
    return [project(r) for r in c.execute(_SELECT + " ORDER BY s.id DESC")]
