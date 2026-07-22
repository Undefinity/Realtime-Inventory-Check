from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime

from flask import Flask, jsonify, render_template, request

from .database import DatabaseError, check_connection
from .services import find_item_by_barcode, get_near_expiry_items


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"无法序列化类型：{type(value)!r}")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        try:
            return jsonify({"ok": True, "database": check_connection()})
        except DatabaseError as error:
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
            return jsonify({"ok": False, "message": str(error)}), 503

    return app
