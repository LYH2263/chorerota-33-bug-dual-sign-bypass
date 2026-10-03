import sqlite3

import pytest

from app.modules import swap_sign, swap_gate, swap_view


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE members(id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE assignments(
            id INTEGER PRIMARY KEY AUTOINCREMENT, week_id INT, day INT,
            task_id INT, member_id INT);
        CREATE TABLE swap_requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT, week_id INT,
            a_day INT, a_task INT, b_day INT, b_task INT,
            status TEXT, note TEXT,
            a_member INT, b_member INT,
            a_signed INT NOT NULL DEFAULT 0, b_signed INT NOT NULL DEFAULT 0,
            a_decision TEXT, b_decision TEXT);
        """
    )
    c.executemany("INSERT INTO members(id,name) VALUES (?,?)", [(1, "阿明"), (2, "小雨")])
    c.executemany(
        "INSERT INTO assignments(week_id,day,task_id,member_id) VALUES (1,?,?,?)",
        [(0, 10, 1), (1, 10, 2)],
    )
    return c


def _make_swap(c, status="pending"):
    cur = c.execute(
        "INSERT INTO swap_requests(week_id,a_day,a_task,b_day,b_task,status,"
        "a_member,b_member) VALUES (1,0,10,1,10,?,1,2)",
        (status,),
    )
    c.commit()
    return cur.lastrowid


def _board(c):
    return {r["day"]: r["member_id"]
            for r in c.execute("SELECT day,member_id FROM assignments ORDER BY day")}


def test_unsigned_confirm_rejected_and_board_unchanged():
    c = _db()
    sid = _make_swap(c)
    with pytest.raises(swap_gate.GateError) as ei:
        swap_gate.confirm(c, sid)
    assert ei.value.reason == "missing_signature"
    assert set(ei.value.missing) == {"a", "b"}
    assert _board(c) == {0: 1, 1: 2}
    assert c.execute("SELECT status FROM swap_requests WHERE id=?", (sid,)).fetchone()["status"] == "pending"


def test_single_signature_confirm_rejected_and_board_unchanged():
    c = _db()
    sid = _make_swap(c)
    swap_sign.register_sign(c, sid, 1, "approve")
    view = {s["id"]: s for s in swap_view.list_swaps(c)}[sid]
    assert view["signed_count"] == 1 and view["ready_to_confirm"] is False
    with pytest.raises(swap_gate.GateError) as ei:
        swap_gate.confirm(c, sid)
    assert ei.value.reason == "missing_signature" and ei.value.missing == ["b"]
    assert _board(c) == {0: 1, 1: 2}
    assert c.execute("SELECT status FROM swap_requests WHERE id=?", (sid,)).fetchone()["status"] == "pending"


def test_signing_alone_never_moves_board():
    c = _db()
    sid = _make_swap(c)
    swap_sign.register_sign(c, sid, 1, "approve")
    swap_sign.register_sign(c, sid, 2, "approve")
    assert _board(c) == {0: 1, 1: 2}
    view = {s["id"]: s for s in swap_view.list_swaps(c)}[sid]
    assert view["signed_count"] == 2 and view["ready_to_confirm"] is True
    assert view["status"] == "pending"


def test_dual_approved_confirm_swaps_board_and_status_together():
    c = _db()
    sid = _make_swap(c)
    swap_sign.register_sign(c, sid, 1, "approve")
    swap_sign.register_sign(c, sid, 2, "approve")
    result = swap_gate.confirm(c, sid)
    assert result["status"] == "confirmed"
    assert _board(c) == {0: 2, 1: 1}
    view = {s["id"]: s for s in swap_view.list_swaps(c)}[sid]
    assert view["status"] == "confirmed"


def test_reject_sets_terminal_status_and_confirm_blocked():
    c = _db()
    sid = _make_swap(c)
    swap_sign.register_sign(c, sid, 1, "approve")
    row = swap_sign.register_sign(c, sid, 2, "reject")
    assert row["status"] == "rejected"
    assert row["b"]["decision"] == "rejected"
    with pytest.raises(swap_gate.GateError) as ei:
        swap_gate.confirm(c, sid)
    assert ei.value.reason == "not_pending"
    assert _board(c) == {0: 1, 1: 2}


def test_confirmed_swap_cannot_confirm_again():
    c = _db()
    sid = _make_swap(c)
    swap_sign.register_sign(c, sid, 1, "approve")
    swap_sign.register_sign(c, sid, 2, "approve")
    swap_gate.confirm(c, sid)
    with pytest.raises(swap_gate.GateError) as ei:
        swap_gate.confirm(c, sid)
    assert ei.value.reason == "not_pending"


def test_gate_keeps_reading_signatures_after_board_already_changed():
    """另一张票确认改表（现场格位已变）后，新票仍须自身双签齐备，
    门禁不改成按当前格位现场重算来绕开签名。"""
    c = _db()
    # 第一张票双签齐备并确认，格位已交换
    first = _make_swap(c)
    swap_sign.register_sign(c, first, 1, "approve")
    swap_sign.register_sign(c, first, 2, "approve")
    swap_gate.confirm(c, first)
    assert _board(c) == {0: 2, 1: 1}
    # 预演票：针对交换后现状再换回来；只签一侧不得确认
    preview = c.execute(
        "INSERT INTO swap_requests(week_id,a_day,a_task,b_day,b_task,status,"
        "a_member,b_member) VALUES (1,0,10,1,10,'pending',2,1)"
    ).lastrowid
    c.commit()
    swap_sign.register_sign(c, preview, 2, "approve")
    with pytest.raises(swap_gate.GateError) as ei:
        swap_gate.confirm(c, preview)
    assert ei.value.reason == "missing_signature"
    assert _board(c) == {0: 2, 1: 1}
    # 补齐双签后确认成功，格位换回
    swap_sign.register_sign(c, preview, 1, "approve")
    swap_gate.confirm(c, preview)
    assert _board(c) == {0: 1, 1: 2}
