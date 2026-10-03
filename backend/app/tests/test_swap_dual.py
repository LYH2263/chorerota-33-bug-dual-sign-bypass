import pytest

from app import seed
from app.db import connect
from app.engines.rota import build_week_slots
from app.modules import swap_gate, swap_sign, swap_view

WEEK_ID = 1
# (day0,task1)=阿明(1), (day1,task1)=爷爷(3) —— 不同当事方的两格
A_DAY, A_TASK, A_MEMBER = 0, 1, 1
B_DAY, B_TASK, B_MEMBER = 1, 1, 3


@pytest.fixture()
def c(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    conn = connect()
    for s in build_week_slots([1, 2, 3], [1, 2], days=7):
        conn.execute(
            "INSERT INTO assignments(week_id,day,task_id,member_id) VALUES (1,?,?,?)",
            (s["day"], s["task_id"], s["member_id"]),
        )
    conn.commit()
    yield conn
    conn.close()


def _open_swap(conn):
    cur = conn.execute(
        "INSERT INTO swap_requests(week_id,a_day,a_task,b_day,b_task,status,"
        "a_member,b_member,a_signed,b_signed) VALUES (1,?,?,?,?, 'pending',?,?,0,0)",
        (A_DAY, A_TASK, B_DAY, B_TASK, A_MEMBER, B_MEMBER),
    )
    conn.commit()
    return cur.lastrowid


def _board(conn):
    return {
        (r["day"], r["task_id"]): r["member_id"]
        for r in conn.execute(
            "SELECT day,task_id,member_id FROM assignments WHERE week_id=? ORDER BY day,task_id",
            (WEEK_ID,),
        )
    }


def _status(conn, sid):
    return conn.execute("SELECT status FROM swap_requests WHERE id=?", (sid,)).fetchone()["status"]


def test_confirm_blocked_with_no_signatures_board_unchanged(c):
    sid = _open_swap(c)
    before = _board(c)
    with pytest.raises(swap_gate.GateError) as ei:
        swap_gate.confirm(c, sid)
    assert ei.value.reason == "missing_signatures"
    assert ei.value.missing == ["a", "b"]
    assert _board(c) == before
    assert _status(c, sid) == "pending"
    row = swap_view.list_swaps(c)[0]
    assert row["ready_to_confirm"] is False and row["signed_count"] == 0


@pytest.mark.parametrize("side,member,missing", [("a", A_MEMBER, "b"), ("b", B_MEMBER, "a")])
def test_confirm_blocked_with_one_signature(c, side, member, missing):
    sid = _open_swap(c)
    before = _board(c)
    swap_sign.register_sign(c, sid, member, "approve")
    assert _board(c) == before  # 签名本身不改格
    with pytest.raises(swap_gate.GateError) as ei:
        swap_gate.confirm(c, sid)
    assert ei.value.reason == "missing_signatures"
    assert ei.value.missing == [missing]
    assert _board(c) == before
    assert _status(c, sid) == "pending"


def test_dual_approve_then_confirm_exchanges_board(c):
    sid = _open_swap(c)
    before = _board(c)
    swap_sign.register_sign(c, sid, A_MEMBER, "approve")
    swap_sign.register_sign(c, sid, B_MEMBER, "approve")
    # 双签齐备但未确认：签名动作绝不动格
    assert _board(c) == before
    row = next(r for r in swap_view.list_swaps(c) if r["id"] == sid)
    assert row["ready_to_confirm"] is True and row["signed_count"] == 2

    result = swap_gate.confirm(c, sid)
    assert result["status"] == "confirmed"
    after = _board(c)
    assert after[(A_DAY, A_TASK)] == B_MEMBER
    assert after[(B_DAY, B_TASK)] == A_MEMBER
    # 仅两格交换，其余格位不变
    assert {k: v for k, v in after.items() if k != (A_DAY, A_TASK) and k != (B_DAY, B_TASK)} == {
        k: v for k, v in before.items() if k != (A_DAY, A_TASK) and k != (B_DAY, B_TASK)
    }
    row = next(r for r in swap_view.list_swaps(c) if r["id"] == sid)
    assert row["status"] == "confirmed" and row["ready_to_confirm"] is False


def test_reject_is_terminal_and_never_moves_board(c):
    sid = _open_swap(c)
    before = _board(c)
    row = swap_sign.register_sign(c, sid, A_MEMBER, "reject")
    assert row["status"] == "rejected"
    assert _board(c) == before
    # 另一方也不能再签
    with pytest.raises(swap_sign.SignError) as ei:
        swap_sign.register_sign(c, sid, B_MEMBER, "approve")
    assert ei.value.reason == "not_pending"
    # rejected 不可再确认改表
    with pytest.raises(swap_gate.GateError) as ge:
        swap_gate.confirm(c, sid)
    assert ge.value.reason == "not_pending"
    assert _board(c) == before
    assert _status(c, sid) == "rejected"


def test_confirmed_is_terminal(c):
    sid = _open_swap(c)
    swap_sign.register_sign(c, sid, A_MEMBER, "approve")
    swap_sign.register_sign(c, sid, B_MEMBER, "approve")
    swap_gate.confirm(c, sid)
    with pytest.raises(swap_gate.GateError) as ei:
        swap_gate.confirm(c, sid)
    assert ei.value.reason == "not_pending"
    with pytest.raises(swap_sign.SignError) as se:
        swap_sign.register_sign(c, sid, A_MEMBER, "approve")
    assert se.value.reason == "not_pending"


def test_unassigned_party_blocks_confirm(c):
    sid = _open_swap(c)
    c.execute("UPDATE swap_requests SET a_member=NULL WHERE id=?", (sid,))
    c.commit()
    with pytest.raises(swap_gate.GateError) as ei:
        swap_gate.confirm(c, sid)
    assert ei.value.reason == "missing_signatures"
    assert "a" in ei.value.missing
    assert _status(c, sid) == "pending"


def test_gate_keys_on_signatures_not_on_fly_recompute(c):
    # 即便对调在当前看板上仍合法，缺签名也不得借现场重算绕开门禁
    sid = _open_swap(c)
    before = _board(c)
    with pytest.raises(swap_gate.GateError):
        swap_gate.confirm(c, sid)
    assert _board(c) == before

    # 双签齐备后看板已被他处改动致两格同一人：确认应安全失败，
    # 不置 confirmed、不破坏周格，而不是绕开签名改走重算。
    swap_sign.register_sign(c, sid, A_MEMBER, "approve")
    swap_sign.register_sign(c, sid, B_MEMBER, "approve")
    c.execute(
        "UPDATE assignments SET member_id=? WHERE week_id=? AND day=? AND task_id=?",
        (A_MEMBER, WEEK_ID, B_DAY, B_TASK),
    )
    c.commit()
    mutated = _board(c)
    with pytest.raises(swap_gate.GateError) as ei:
        swap_gate.confirm(c, sid)
    assert ei.value.reason == "same_assignee"
    assert _board(c) == mutated
    assert _status(c, sid) == "pending"
