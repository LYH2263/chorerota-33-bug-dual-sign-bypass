from app.db import connect

def init_db():
    c = connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY, name TEXT, active INT, data_quality TEXT);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, title TEXT, weight INT, data_quality TEXT);
    CREATE TABLE IF NOT EXISTS weeks(id INTEGER PRIMARY KEY, label TEXT, status TEXT);
    CREATE TABLE IF NOT EXISTS assignments(id INTEGER PRIMARY KEY AUTOINCREMENT, week_id INT, day INT, task_id INT, member_id INT);
    CREATE TABLE IF NOT EXISTS swap_requests(id INTEGER PRIMARY KEY AUTOINCREMENT, week_id INT, a_day INT, a_task INT, b_day INT, b_task INT, status TEXT, note TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    _migrate_swap_dual_sign(c)
    if c.execute("SELECT COUNT(*) c FROM members").fetchone()["c"] == 0:
        c.executemany("INSERT INTO members(name,active,data_quality) VALUES (?,?,?)", [
            ("阿明", 1, "clean"), ("小雨", 1, "clean"), ("爷爷", 1, "clean"),
            ("幽灵成员", 0, "dirty"),
        ])
        c.executemany("INSERT INTO tasks(title,weight,data_quality) VALUES (?,?,?)", [
            ("洗碗", 1, "clean"), ("倒垃圾", 1, "clean"), ("扫地", 2, "clean"),
            ("负权重任务", -1, "dirty"),
        ])
        c.execute("INSERT INTO weeks(label,status) VALUES ('第12周','draft')")
        c.execute("INSERT INTO settings(key,value) VALUES ('household','绿纸之家')")
        c.commit()
    c.close()

def _migrate_swap_dual_sign(c):
    """Add dual-sign columns to swap_requests (idempotent for pre-existing DBs)."""
    cols = {r["name"] for r in c.execute("PRAGMA table_info(swap_requests)")}
    for col, ddl in [
        ("a_member", "ALTER TABLE swap_requests ADD COLUMN a_member INT"),
        ("b_member", "ALTER TABLE swap_requests ADD COLUMN b_member INT"),
        ("a_signed", "ALTER TABLE swap_requests ADD COLUMN a_signed INT NOT NULL DEFAULT 0"),
        ("b_signed", "ALTER TABLE swap_requests ADD COLUMN b_signed INT NOT NULL DEFAULT 0"),
        ("a_decision", "ALTER TABLE swap_requests ADD COLUMN a_decision TEXT"),
        ("b_decision", "ALTER TABLE swap_requests ADD COLUMN b_decision TEXT"),
    ]:
        if col not in cols:
            c.execute(ddl)
    c.commit()
