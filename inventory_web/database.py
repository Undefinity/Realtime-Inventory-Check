"""SQL Server 连接配置。密码只从 .env 读取，不写入源码。"""

from __future__ import annotations

import os
from pathlib import Path

import pyodbc


class DatabaseError(RuntimeError):
    pass


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key.strip()] = value


_load_env(Path(__file__).resolve().parents[1] / ".env")


def _driver() -> str:
    configured = os.getenv("SQLSERVER_DRIVER")
    if configured:
        return configured
    installed = set(pyodbc.drivers())
    for name in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"):
        if name in installed:
            return name
    raise DatabaseError("未找到 SQL Server ODBC 驱动，请安装 ODBC Driver 18。")


def get_connection() -> pyodbc.Connection:
    host = os.getenv("SQLSERVER_HOST", "121.43.166.99")
    port = os.getenv("SQLSERVER_PORT", "2433")
    database = os.getenv("SQLSERVER_DATABASE", "bwshopsy_01")
    username = os.getenv("SQLSERVER_USERNAME", "inventory_app")
    password = os.getenv("SQLSERVER_PASSWORD")
    encrypt = os.getenv("SQLSERVER_ENCRYPT", "no")
    if not password:
        raise DatabaseError("未设置 SQLSERVER_PASSWORD，请在 .env 中填写数据库密码。")
    driver = _driver()
    text = (
        f"DRIVER={{{driver}}};SERVER=tcp:{host},{port};DATABASE={database};"
        f"UID={username};PWD={password};"
    )
    if driver == "SQL Server":
        text += "Network=DBMSSOCN;"
    else:
        text += f"TrustServerCertificate=yes;Encrypt={encrypt};"
    try:
        return pyodbc.connect(text, timeout=10)
    except pyodbc.Error as error:
        raise DatabaseError(f"数据库连接失败：{error}") from error


def check_connection() -> dict[str, str]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT DB_NAME(), @@SERVERNAME")
        database, server = cursor.fetchone()
    return {"name": database, "server": server}
