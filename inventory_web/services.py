"""库存与临期查询服务，所有查询均使用参数化 SQL。"""

from __future__ import annotations

from .database import DatabaseError, get_connection


def _rows(cursor):
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def find_item_by_barcode(barcode: str, branch_no: str | None) -> dict:
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""
                WITH matched_items AS (
                    SELECT item_no FROM dbo.bi_t_item_info WHERE barcode = ?
                    UNION
                    SELECT item_no FROM dbo.bi_t_item_barcode WHERE barcode = ?
                )
                SELECT i.item_no, i.item_name, i.item_subname, i.barcode AS master_barcode,
                       i.valid_day, i.tip_day1, i.tip_day2,
                       COALESCE(SUM(CASE WHEN ? IS NULL OR s.branch_no = ?
                                         THEN COALESCE(s.stock_qty, 0) ELSE 0 END), 0) AS stock_qty,
                       COUNT(DISTINCT CASE WHEN ? IS NULL OR s.branch_no = ? THEN s.branch_no END) AS branch_count
                FROM matched_items m
                JOIN dbo.bi_t_item_info i ON i.item_no = m.item_no
                LEFT JOIN dbo.ic_t_branch_stock s ON s.item_no = i.item_no
                GROUP BY i.item_no, i.item_name, i.item_subname, i.barcode,
                         i.valid_day, i.tip_day1, i.tip_day2;
            """, barcode, barcode, branch_no, branch_no, branch_no, branch_no)
            items = _rows(cursor)
            if not items:
                return {"found": False, "barcode": barcode, "message": "未找到对应商品。"}
            cursor.execute("""
                WITH matched_items AS (
                    SELECT item_no FROM dbo.bi_t_item_info WHERE barcode = ?
                    UNION
                    SELECT item_no FROM dbo.bi_t_item_barcode WHERE barcode = ?
                )
                SELECT s.branch_no, s.item_no, SUM(COALESCE(s.stock_qty, 0)) AS stock_qty
                FROM dbo.ic_t_branch_stock s
                JOIN matched_items m ON m.item_no = s.item_no
                WHERE ? IS NULL OR s.branch_no = ?
                GROUP BY s.branch_no, s.item_no
                ORDER BY s.branch_no, s.item_no;
            """, barcode, barcode, branch_no, branch_no)
            return {
                "found": True,
                "barcode": barcode,
                "branch": branch_no,
                "items": items,
                "stock_by_branch": _rows(cursor),
            }
    except DatabaseError:
        raise
    except Exception as error:
        raise DatabaseError(f"库存查询失败：{error}") from error


def get_near_expiry_items(branch_no: str | None, days: int, limit: int):
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT TOP (?) s.branch_no, s.item_no, i.item_name, s.batch_no,
                       s.factory_date, s.valid_date,
                       SUM(COALESCE(s.stock_qty, 0)) AS stock_qty,
                       DATEDIFF(day, CAST(GETDATE() AS date), CAST(s.valid_date AS date)) AS days_to_expiry
                FROM dbo.ic_t_branch_stock_more s
                JOIN dbo.bi_t_item_info i ON i.item_no = s.item_no
                WHERE s.valid_date IS NOT NULL
                  -- “临期”只表示从今天起未来 N 天内到期；已经过期的批次不混入结果。
                  -- 这样 days 参数会直接决定返回范围，避免过期历史记录占满展示上限。
                  AND CAST(s.valid_date AS date) >= CAST(GETDATE() AS date)
                  AND CAST(s.valid_date AS date) < DATEADD(day, ?, CAST(GETDATE() AS date))
                  AND (? IS NULL OR s.branch_no = ?)
                GROUP BY s.branch_no, s.item_no, i.item_name, s.batch_no, s.factory_date, s.valid_date
                ORDER BY s.valid_date, s.branch_no, s.item_no;
            """, limit, days + 1, branch_no, branch_no)
            return _rows(cursor)
    except DatabaseError:
        raise
    except Exception as error:
        raise DatabaseError(f"临期库存查询失败：{error}") from error
