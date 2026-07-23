from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime
from time import perf_counter

from flask import Flask, g, jsonify, render_template, request

from .database import DatabaseError, check_connection
from .services import find_item_by_barcode, get_inventory_items, get_near_expiry_items
from .counting import assign_category, categories, clear_stocktakes, create_category, initialize, save_stocktake, stocktakes


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"无法序列化类型：{type(value)!r}")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    initialize()

    @app.before_request
    def start_request_timer():
        g.request_started_at = perf_counter()

    @app.after_request
    def log_request(response):
        started_at = getattr(g, "request_started_at", None)
        elapsed_ms = (perf_counter() - started_at) * 1000 if started_at is not None else 0
        app.logger.info("%s %s -> %s (%.0f ms)", request.method, request.full_path, response.status_code, elapsed_ms)
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        try:
            return jsonify({"ok": True, "database": check_connection()})
        except DatabaseError as error:
            app.logger.warning("数据库健康检查失败：%s", error)
            return jsonify({"ok": False, "message": str(error)}), 503

    @app.get("/api/lookup")
    def lookup():
        barcode = request.args.get("barcode", "").strip()
        branch = request.args.get("branch", "").strip() or None
        if not barcode:
            return jsonify({"ok": False, "message": "请输入或扫描商品条码。"}), 400
        try:
            result = find_item_by_barcode(barcode, branch)
            return app.response_class(
                response=app.json.dumps({"ok": True, **result}, default=_json_safe),
                status=200,
                mimetype="application/json",
            )
        except DatabaseError as error:
            app.logger.warning("库存查询失败：%s", error)
            return jsonify({"ok": False, "message": str(error)}), 503

    @app.get("/api/near-expiry")
    def near_expiry():
        branch = request.args.get("branch", "").strip() or None
        try:
            days = max(0, min(int(request.args.get("days", 30)), 3650))
            limit = max(1, min(int(request.args.get("limit", 200)), 1000))
        except ValueError:
            return jsonify({"ok": False, "message": "临期天数和条数必须为数字。"}), 400
        try:
            rows = get_near_expiry_items(branch, days, limit)
            return app.response_class(
                response=app.json.dumps(
                    {"ok": True, "branch": branch, "days": days, "rows": rows}, default=_json_safe
                ),
                status=200,
                mimetype="application/json",
            )
        except DatabaseError as error:
            app.logger.warning("临期库存查询失败：%s", error)
            return jsonify({"ok": False, "message": str(error)}), 503

    @app.get("/api/inventory")
    def inventory():
        branch = request.args.get("branch", "").strip() or None
        try:
            rows = get_inventory_items(branch)
            return app.response_class(
                response=app.json.dumps({"ok": True, "branch": branch, "rows": rows}, default=_json_safe),
                status=200,
                mimetype="application/json",
            )
        except DatabaseError as error:
            app.logger.warning("库存总览查询失败：%s", error)
            return jsonify({"ok": False, "message": str(error)}), 503

    @app.get("/api/categories")
    def get_categories():
        return jsonify({"ok": True, "rows": categories()})

    @app.post("/api/categories")
    def add_category():
        try:
            return jsonify({"ok": True, "category": create_category((request.get_json(silent=True) or {}).get("name", ""))})
        except ValueError as error:
            return jsonify({"ok": False, "message": str(error)}), 400

    @app.post("/api/item-category")
    def set_item_category():
        payload = request.get_json(silent=True) or {}
        try:
            assign_category(str(payload.get("item_no", "")).strip(), payload.get("category_id"))
            return jsonify({"ok": True})
        except ValueError as error:
            return jsonify({"ok": False, "message": str(error)}), 400

    @app.get("/api/stocktakes")
    def get_stocktakes():
        category_id = request.args.get("category_id", type=int)
        return jsonify({"ok": True, "rows": stocktakes(request.args.get("branch", "").strip() or None, category_id)})

    @app.post("/api/stocktakes")
    def add_stocktake():
        payload = request.get_json(silent=True) or {}
        try:
            quantity = float(payload.get("counted_qty"))
            if quantity < 0:
                raise ValueError("盘点数量不能小于 0。")
            return jsonify({"ok": True, **save_stocktake(str(payload.get("item_no", "")).strip(), str(payload.get("item_name", "")).strip(), str(payload.get("branch_no", "")).strip(), quantity)})
        except (TypeError, ValueError) as error:
            return jsonify({"ok": False, "message": str(error) or "请输入有效的盘点数量。"}), 400

    @app.post("/api/stocktakes/clear")
    def clear_stocktake():
        try:
            count = clear_stocktakes((request.get_json(silent=True) or {}).get("branch_no", "").strip())
            return jsonify({"ok": True, "deleted": count})
        except ValueError as error:
            return jsonify({"ok": False, "message": str(error)}), 400

    return app
