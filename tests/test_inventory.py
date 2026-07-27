import sqlite3
import unittest
from contextlib import nullcontext

from inventory_web import inventory


class InventorySearchTest(unittest.TestCase):
    def test_search_matches_barcode_and_keywords(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript('''
            CREATE TABLE "库存" (item_no TEXT PRIMARY KEY, item_name TEXT, unit_no TEXT, barcode TEXT);
            CREATE TABLE item_categories (item_no TEXT PRIMARY KEY, category_id INTEGER);
        ''')
        connection.execute(
            'INSERT INTO "库存" (item_no, item_name, unit_no, barcode) VALUES (?, ?, ?, ?)',
            ("I001", "测试商品", "件", "4108450109855"),
        )
        original_connection = inventory._connection
        inventory._connection = lambda: nullcontext(connection)
        try:
            rows, total, _, _ = inventory.search_inventory("4108450109855")
            self.assertEqual(total, 1)
            self.assertEqual(rows[0]["barcode"], "4108450109855")

            rows, total, _, _ = inventory.search_inventory("I00")
            self.assertEqual(total, 1)
            self.assertEqual(rows[0]["item_no"], "I001")

            rows, total, _, _ = inventory.search_inventory("测试")
            self.assertEqual(total, 1)
            self.assertEqual(rows[0]["item_name"], "测试商品")
        finally:
            inventory._connection = original_connection
            connection.close()


if __name__ == "__main__":
    unittest.main()
