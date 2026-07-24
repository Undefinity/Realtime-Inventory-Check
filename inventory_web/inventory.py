"""本地库存主数据，以及按需从外部 SQL Server 同步的服务。"""

from __future__ import annotations

from .counting import _connection
from .database import DatabaseError, get_connection


def _page(page: int, page_size: int) -> tuple[int, int]:
    return max(1, page), min(200, max(1, page_size))


def inventory_items(page: int = 1, page_size: int = 100) -> tuple[list[dict[str, str | None]], int, int, int]:
    """分页读取本地 SQLite 的“库存”表，不连接外部数据库。"""
    page, page_size = _page(page, page_size)
    with _connection() as connection:
        total = connection.execute('SELECT COUNT(*) FROM "库存"').fetchone()[0]
        rows = connection.execute(
            'SELECT item_no, item_name, unit_no FROM "库存" ORDER BY item_no LIMIT ? OFFSET ?',
            (page_size, (page - 1) * page_size),
        ).fetchall()
    return [dict(row) for row in rows], total, page, page_size


def search_inventory(query: str, page: int = 1, page_size: int = 100) -> tuple[list[dict[str, str | None]], int, int, int]:
    """按商品编码或商品名称模糊查询本地库存表。"""
    query = query.strip()
    if not query:
        raise ValueError("请输入商品编码或商品名称。")
    page, page_size = _page(page, page_size)
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    with _connection() as connection:
        total = connection.execute(
            '''SELECT COUNT(*) FROM "库存"
               WHERE item_no LIKE ? ESCAPE '\\' OR item_name LIKE ? ESCAPE '\\' ''',
            (pattern, pattern),
        ).fetchone()[0]
        rows = connection.execute(
            '''SELECT i.item_no, i.item_name, i.unit_no, ic.category_id
               FROM "库存" i
               LEFT JOIN item_categories ic ON ic.item_no = i.item_no
               WHERE i.item_no LIKE ? ESCAPE '\\' OR i.item_name LIKE ? ESCAPE '\\'
               ORDER BY i.item_no LIMIT ? OFFSET ?''',
            (pattern, pattern, page_size, (page - 1) * page_size),
        ).fetchall()
    return [dict(row) for row in rows], total, page, page_size


def sync_inventory() -> int:
    """读取外部商品主数据的指定三列，并以完整快照覆盖本地库存表。"""
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT item_no, item_name, unit_no
                FROM dbo.bi_t_item_info
                ORDER BY item_no
            """)
            rows = [tuple(row) for row in cursor.fetchall()]
    except DatabaseError:
        raise
    except Exception as error:
        raise DatabaseError(f"库存同步读取失败：{error}") from error

    try:
        with _connection() as connection:
            connection.execute('DELETE FROM "库存"')
            connection.executemany(
                'INSERT INTO "库存" (item_no, item_name, unit_no) VALUES (?, ?, ?)', rows
            )
    except Exception as error:
        raise RuntimeError(f"本地库存保存失败：{error}") from error
    return len(rows)
