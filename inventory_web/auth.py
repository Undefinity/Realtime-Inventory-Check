from __future__ import annotations

import sqlite3
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from .counting import _connection


ROLES = {"admin", "user"}


def initialize_users() -> None:
    """Create the local user table and its initial administrator once."""
    with _connection() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        if not conn.execute("SELECT 1 FROM users WHERE username = ?", ("admin",)).fetchone():
            now = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("admin", generate_password_hash("123456"), "admin", now, now),
            )


def authenticate(username: str, password: str) -> dict | None:
    with _connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def list_users() -> list[dict]:
    with _connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT id, username, role, created_at, updated_at FROM users ORDER BY username COLLATE NOCASE"
            )
        ]


def create_user(username: str, password: str, role: str) -> None:
    username, password, role = _validate_user_values(username, password, role, password_required=True)
    now = datetime.now().isoformat(timespec="seconds")
    with _connection() as conn:
        try:
            conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (username, generate_password_hash(password), role, now, now),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("用户名已存在。") from error


def update_user(user_id: int, username: str, password: str, role: str, current_user_id: int) -> None:
    username, password, role = _validate_user_values(username, password, role, password_required=False)
    with _connection() as conn:
        existing = conn.execute("SELECT id, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            raise ValueError("用户不存在。")
        if existing["role"] == "admin" and role != "admin":
            admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
            if admin_count <= 1:
                raise ValueError("系统至少需要保留一名管理员。")
        if existing["id"] == current_user_id and role != "admin":
            raise ValueError("不能取消当前登录账户的管理员权限。")
        values = [username, role, datetime.now().isoformat(timespec="seconds")]
        sql = "UPDATE users SET username = ?, role = ?, updated_at = ?"
        if password:
            sql += ", password_hash = ?"
            values.append(generate_password_hash(password))
        sql += " WHERE id = ?"
        values.append(user_id)
        try:
            conn.execute(sql, values)
        except sqlite3.IntegrityError as error:
            raise ValueError("用户名已存在。") from error


def _validate_user_values(username: str, password: str, role: str, password_required: bool) -> tuple[str, str, str]:
    username = username.strip()
    if not 3 <= len(username) <= 50:
        raise ValueError("用户名长度应为 3 到 50 个字符。")
    if password_required and len(password) < 6:
        raise ValueError("密码至少需要 6 个字符。")
    if password and len(password) < 6:
        raise ValueError("密码至少需要 6 个字符。")
    if role not in ROLES:
        raise ValueError("用户类型只能是管理员或用户。")
    return username, password, role
