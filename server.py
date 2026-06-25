#!/usr/bin/env python3
"""
業務タスク管理システム - ローカルAPIサーバー
=============================================
使い方:
    python server.py

ブラウザで http://localhost:8080 を開いてください。

依存: Python 3.6以上（標準ライブラリのみ・追加インストール不要）
データ: task_management.db（同フォルダに自動作成）
"""

import json
import os
import re
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# ─────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────
PORT     = 8080
DB_PATH  = Path(__file__).parent / "task_management.db"
HTML_DIR = Path(__file__).parent   # HTMLファイルと同じフォルダ


# ─────────────────────────────────────────────
# データベース初期化
# ─────────────────────────────────────────────
def init_db():
    """テーブルが存在しない場合だけ作成する（べき等）"""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # タスクテーブル
    # steps / checks / checksDone は JSON 文字列で格納
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id            INTEGER PRIMARY KEY,
            name          TEXT    NOT NULL,
            type          TEXT    DEFAULT '',
            created       TEXT    DEFAULT '',
            deadline      TEXT    DEFAULT '',
            completedDate TEXT    DEFAULT '',
            memo          TEXT    DEFAULT '',
            status        TEXT    DEFAULT 'active',
            steps         TEXT    DEFAULT '[]',
            checks        TEXT    DEFAULT '[]',
            checksDone    TEXT    DEFAULT '[]'
        )
    """)

    # タスク種類テーブル
    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_types (
            key        TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            recurring  INTEGER DEFAULT 0,
            steps      TEXT    DEFAULT '[]',
            checks     TEXT    DEFAULT '[]'
        )
    """)

    con.commit()
    con.close()
    print(f"[DB] データベース: {DB_PATH}")


def get_con():
    """DB接続を返す（row_factory 付き）"""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ─────────────────────────────────────────────
# タスク Row → dict 変換
# ─────────────────────────────────────────────
def row_to_task(row):
    d = dict(row)
    for key in ("steps", "checks", "checksDone"):
        try:
            d[key] = json.loads(d.get(key) or "[]")
        except Exception:
            d[key] = []
    return d


def row_to_type(row):
    d = dict(row)
    for key in ("steps", "checks"):
        try:
            d[key] = json.loads(d.get(key) or "[]")
        except Exception:
            d[key] = []
    d["recurring"] = bool(d.get("recurring", 0))
    return d


# ─────────────────────────────────────────────
# リクエストハンドラー
# ─────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    # ── ログを整形して表示 ──────────────────────
    def log_message(self, fmt, *args):
        print(f"  {self.command} {self.path}  →  {args[1]}")

    # ── レスポンス送信ヘルパー ──────────────────
    def send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, "File not found")
            return
        ext = path.suffix.lower()
        mime = {
            ".html": "text/html; charset=utf-8",
            ".js":   "application/javascript; charset=utf-8",
            ".css":  "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png":  "image/png",
            ".ico":  "image/x-icon",
        }.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # ── OPTIONS (CORS プリフライト) ─────────────
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ══════════════════════════════════════════
    # GET
    # ══════════════════════════════════════════
    def do_GET(self):
        path = self.path.split("?")[0]

        # ── ルートアクセス → HTML ──────────────
        if path == "/" or path == "/index.html":
            html = HTML_DIR / "task_management.html"
            self.send_file(html)
            return

        # ── 静的ファイル（CSS/JS等） ───────────
        if not path.startswith("/api/"):
            file_path = HTML_DIR / path.lstrip("/")
            self.send_file(file_path)
            return

        # ══ API ══════════════════════════════

        # GET /api/tasks  → 全タスク取得
        if path == "/api/tasks":
            con = get_con()
            rows = con.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
            con.close()
            self.send_json(200, {"data": [row_to_task(r) for r in rows]})
            return

        # GET /api/tasks/:id  → 1件取得
        m = re.fullmatch(r"/api/tasks/(\d+)", path)
        if m:
            tid = int(m.group(1))
            con = get_con()
            row = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
            con.close()
            if row:
                self.send_json(200, {"data": row_to_task(row)})
            else:
                self.send_json(404, {"error": "not found"})
            return

        # GET /api/task_types  → 全種類取得
        if path == "/api/task_types":
            con = get_con()
            rows = con.execute("SELECT * FROM task_types ORDER BY rowid").fetchall()
            con.close()
            self.send_json(200, {"data": [row_to_type(r) for r in rows]})
            return

        self.send_json(404, {"error": "not found"})

    # ══════════════════════════════════════════
    # POST（新規作成）
    # ══════════════════════════════════════════
    def do_POST(self):
        path = self.path.split("?")[0]
        body = self.read_body()

        # POST /api/tasks
        if path == "/api/tasks":
            con = get_con()
            con.execute("""
                INSERT OR REPLACE INTO tasks
                  (id, name, type, created, deadline, completedDate, memo, status, steps, checks, checksDone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                body.get("id"),
                body.get("name", ""),
                body.get("type", ""),
                body.get("created", ""),
                body.get("deadline", ""),
                body.get("completedDate", ""),
                body.get("memo", ""),
                body.get("status", "active"),
                json.dumps(body.get("steps",      []), ensure_ascii=False),
                json.dumps(body.get("checks",     []), ensure_ascii=False),
                json.dumps(body.get("checksDone", []), ensure_ascii=False),
            ))
            con.commit()
            con.close()
            self.send_json(201, {"ok": True})
            return

        # POST /api/task_types
        if path == "/api/task_types":
            con = get_con()
            con.execute("""
                INSERT OR REPLACE INTO task_types (key, name, recurring, steps, checks)
                VALUES (?, ?, ?, ?, ?)
            """, (
                body.get("key"),
                body.get("name", ""),
                1 if body.get("recurring") else 0,
                json.dumps(body.get("steps",  []), ensure_ascii=False),
                json.dumps(body.get("checks", []), ensure_ascii=False),
            ))
            con.commit()
            con.close()
            self.send_json(201, {"ok": True})
            return

        self.send_json(404, {"error": "not found"})

    # ══════════════════════════════════════════
    # PUT（更新）
    # ══════════════════════════════════════════
    def do_PUT(self):
        path = self.path.split("?")[0]
        body = self.read_body()

        # PUT /api/tasks/:id
        m = re.fullmatch(r"/api/tasks/(\d+)", path)
        if m:
            tid = int(m.group(1))
            con = get_con()
            con.execute("""
                UPDATE tasks SET
                  name=?, type=?, created=?, deadline=?, completedDate=?,
                  memo=?, status=?, steps=?, checks=?, checksDone=?
                WHERE id=?
            """, (
                body.get("name", ""),
                body.get("type", ""),
                body.get("created", ""),
                body.get("deadline", ""),
                body.get("completedDate", ""),
                body.get("memo", ""),
                body.get("status", "active"),
                json.dumps(body.get("steps",      []), ensure_ascii=False),
                json.dumps(body.get("checks",     []), ensure_ascii=False),
                json.dumps(body.get("checksDone", []), ensure_ascii=False),
                tid,
            ))
            con.commit()
            con.close()
            self.send_json(200, {"ok": True})
            return

        # PUT /api/task_types/:key
        m = re.fullmatch(r"/api/task_types/([^/]+)", path)
        if m:
            key = m.group(1)
            con = get_con()
            con.execute("""
                UPDATE task_types SET name=?, recurring=?, steps=?, checks=?
                WHERE key=?
            """, (
                body.get("name", ""),
                1 if body.get("recurring") else 0,
                json.dumps(body.get("steps",  []), ensure_ascii=False),
                json.dumps(body.get("checks", []), ensure_ascii=False),
                key,
            ))
            con.commit()
            con.close()
            self.send_json(200, {"ok": True})
            return

        self.send_json(404, {"error": "not found"})

    # ══════════════════════════════════════════
    # DELETE（削除）
    # ══════════════════════════════════════════
    def do_DELETE(self):
        path = self.path.split("?")[0]

        # DELETE /api/tasks/:id
        m = re.fullmatch(r"/api/tasks/(\d+)", path)
        if m:
            tid = int(m.group(1))
            con = get_con()
            con.execute("DELETE FROM tasks WHERE id=?", (tid,))
            con.commit()
            con.close()
            self.send_json(200, {"ok": True})
            return

        # DELETE /api/task_types/:key
        m = re.fullmatch(r"/api/task_types/([^/]+)", path)
        if m:
            key = m.group(1)
            con = get_con()
            con.execute("DELETE FROM task_types WHERE key=?", (key,))
            con.commit()
            con.close()
            self.send_json(200, {"ok": True})
            return

        self.send_json(404, {"error": "not found"})


# ─────────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    server = HTTPServer(("localhost", PORT), Handler)
    print("=" * 50)
    print("  業務タスク管理システム - サーバー起動中")
    print(f"  URL  : http://localhost:{PORT}")
    print(f"  DB   : {DB_PATH}")
    print("  終了 : Ctrl + C")
    print("=" * 50)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[サーバー停止]")
        server.server_close()
        sys.exit(0)
