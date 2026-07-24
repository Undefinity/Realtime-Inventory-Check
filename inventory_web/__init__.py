from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime
from time import perf_counter

import os
import secrets
from hmac import compare_digest
from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for

from .database import DatabaseError, check_connection
from .services import find_item_by_barcode, get_inventory_items, get_near_expiry_items
from .counting import assign_category, categories, clear_stocktakes, create_category, initialize, save_stocktake, stocktakes
from .auth import authenticate, create_user, initialize_users, list_users, update_user


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"无法序列化类型：{type(value)!r}")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.config.update(
        SECRET_KEY=_session_secret(),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
    )
    initialize()
    initialize_users()

    @app.context_processor
    def inject_csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(24)
            session["csrf_token"] = token
        return {"csrf_token": token}

    def csrf_valid() -> bool:
        return compare_digest(session.get("csrf_token", ""), request.form.get("csrf_token", ""))

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("role") != "admin":
                flash("仅管理员可以访问用户管理。", "error")
                return redirect(url_for("index"))
            return view(*args, **kwargs)
        return wrapped

    @app.before_request
    def start_request_timer():
        g.request_started_at = perf_counter()
        if request.endpoint in {"login", "static"}:
            return None
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "message": "登录已失效，请重新登录。"}), 401
            return redirect(url_for("login", next=request.full_path))
        return None

    @app.after_request
    def log_request(response):
        started_at = getattr(g, "request_started_at", None)
        elapsed_ms = (perf_counter() - started_at) * 1000 if started_at is not None else 0
        app.logger.info("%s %s -> %s (%.0f ms)", request.method, request.full_path, response.status_code, elapsed_ms)
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("user_id"):
            return redirect(url_for("index"))
        error = None
        if request.method == "POST":
            if not csrf_valid():
                error = "页面已过期，请刷新后重试。"
                return render_template("login.html", error=error), 400
            user = authenticate(request.form.get("username", ""), request.form.get("password", ""))
            if user:
                session.clear()
                session.permanent = True
                session.update({"user_id": user["id"], "username": user["username"], "role": user["role"]})
                target = request.args.get("next", "")
                return redirect(target if target.startswith("/") and not target.startswith("//") else url_for("index"))
            error = "用户名或密码错误。"
        return render_template("login.html", error=error)

    @app.post("/logout")
    def logout():
        if not csrf_valid():
            return "页面已过期，请刷新后重试。", 400
        session.clear()
        return redirect(url_for("login"))

    @app.route("/admin/users", methods=["GET", "POST"])
    @admin_required
    def manage_users():
        if request.method == "POST":
            try:
                if not csrf_valid():
                    raise ValueError("页面已过期，请刷新后重试。")
                action = request.form.get("action")
                if action == "create":
                    create_user(request.form.get("username", ""), request.form.get("password", ""), request.form.get("role", "user"))
                    flash("用户已创建。", "success")
                elif action == "update":
                    update_user(int(request.form["user_id"]), request.form.get("username", ""), request.form.get("password", ""), request.form.get("role", "user"), session["user_id"])
                    flash("用户信息已更新。", "success")
                else:
                    raise ValueError("不支持的操作。")
            except (KeyError, ValueError) as error:
                flash(str(error), "error")
            return redirect(url_for("manage_users"))
        return render_template("users.html", users=list_users())

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


def _session_secret() -> str:
    """Use an env-provided secret, or retain a generated local secret across restarts."""
    configured = os.getenv("FLASK_SECRET_KEY")
    if configured:
        return configured
    secret_path = Path(__file__).resolve().parents[1] / "data" / ".session_secret"
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    secret_path.parent.mkdir(exist_ok=True)
    secret = secrets.token_urlsafe(32)
    secret_path.write_text(secret, encoding="utf-8")
    return secret
