from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "stocktake.db"


def _connection():
    DATABASE_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize() -> None:
    with _connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS "库存" (
                item_no TEXT PRIMARY KEY NOT NULL,
                item_name TEXT NOT NULL,
                unit_no TEXT,
                barcode TEXT
            );
            CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS item_categories (item_no TEXT PRIMARY KEY, category_id INTEGER NOT NULL REFERENCES categories(id));
            CREATE TABLE IF NOT EXISTS stocktakes (
                item_no TEXT NOT NULL, branch_no TEXT NOT NULL, item_name TEXT NOT NULL,
                counted_qty REAL NOT NULL, counted_at TEXT NOT NULL,
                PRIMARY KEY (item_no, branch_no)
            );
        """)
        # 已部署的旧版本没有条码列；以迁移方式保留原有盘点和分类数据。
        columns = {row["name"] for row in conn.execute('PRAGMA table_info("库存")')}
        if "barcode" not in columns:
            conn.execute('ALTER TABLE "库存" ADD COLUMN barcode TEXT')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_inventory_barcode ON "库存"(barcode)')


def categories():
    with _connection() as conn:
        return [dict(row) for row in conn.execute("SELECT id, name FROM categories ORDER BY name")]


def create_category(name: str):
    name = name.strip()
    if not name:
        raise ValueError("请输入分类名称。")
    with _connection() as conn:
        try:
            cursor = conn.execute("INSERT INTO categories(name, created_at) VALUES (?, ?)", (name, datetime.now().isoformat(timespec="seconds")))
        except sqlite3.IntegrityError as error:
            raise ValueError("该分类已存在。") from error
        return {"id": cursor.lastrowid, "name": name}


def rename_category(category_id: int, name: str):
    name = name.strip()
    if not name:
        raise ValueError("请输入分类名称。")
    with _connection() as conn:
        try:
            cursor = conn.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
        except sqlite3.IntegrityError as error:
            raise ValueError("该分类已存在。") from error
        if not cursor.rowcount:
            raise ValueError("分类不存在。")


def delete_category(category_id: int):
    with _connection() as conn:
        if not conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone():
            raise ValueError("分类不存在。")
        conn.execute("DELETE FROM item_categories WHERE category_id = ?", (category_id,))
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))


def assign_category(item_no: str, category_id: int | None):
    with _connection() as conn:
        if category_id is None:
            conn.execute("DELETE FROM item_categories WHERE item_no = ?", (item_no,))
        else:
            if not conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone():
                raise ValueError("分类不存在。")
            conn.execute("INSERT INTO item_categories(item_no, category_id) VALUES (?, ?) ON CONFLICT(item_no) DO UPDATE SET category_id = excluded.category_id", (item_no, category_id))


def save_stocktake(item_no: str, item_name: str, branch_no: str, counted_qty: float):
    if not item_no or not item_name or not branch_no:
        raise ValueError("商品、商品名称和盘点门店不能为空。")
    now = datetime.now().isoformat(timespec="seconds")
    with _connection() as conn:
        conn.execute("""INSERT INTO stocktakes(item_no, branch_no, item_name, counted_qty, counted_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(item_no, branch_no) DO UPDATE SET item_name=excluded.item_name, counted_qty=excluded.counted_qty, counted_at=excluded.counted_at""", (item_no, branch_no, item_name, counted_qty, now))
    return {"counted_at": now}


def stocktakes(branch_no: str | None, category_id: int | None):
    sql = """SELECT s.item_no, s.item_name, s.branch_no, s.counted_qty, s.counted_at, c.id AS category_id, c.name AS category_name,
        EXISTS(SELECT 1 FROM stocktakes other WHERE other.item_no=s.item_no AND other.branch_no <> s.branch_no) AS counted_by_other
        FROM stocktakes s LEFT JOIN item_categories ic ON ic.item_no=s.item_no LEFT JOIN categories c ON c.id=ic.category_id WHERE 1=1"""
    values = []
    if branch_no:
        sql += " AND s.branch_no = ?"; values.append(branch_no)
    if category_id:
        sql += " AND c.id = ?"; values.append(category_id)
    sql += " ORDER BY s.counted_at DESC"
    with _connection() as conn:
        return [dict(row) for row in conn.execute(sql, values)]


def clear_stocktakes(branch_no: str):
    if not branch_no:
        raise ValueError("请先填写盘点门店编号，再执行清空。")
    with _connection() as conn:
        cursor = conn.execute("DELETE FROM stocktakes WHERE branch_no = ?", (branch_no,))
    return cursor.rowcount
