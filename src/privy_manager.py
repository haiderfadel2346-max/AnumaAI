#!/usr/bin/env python3
"""
Anuma AI Registration Manager — Web UI for batch account registration.
"""
import json
import os
import sqlite3
import threading
import time
import base64
import logging
import random
import string
from datetime import datetime
from queue import Queue, Empty
from typing import Any, Dict, Optional

from flask import Flask, render_template, request, jsonify

from anuma_client import AnumaClient
from config import (
    DB_PATH, MAIL_API_KEY,
    MANAGER_PORT, DEFAULT_TOTAL, DEFAULT_CONCURRENCY,
    DEFAULT_TIMEOUT, DEFAULT_INTERVAL, DEFAULT_DOMAIN, validate, get_proxies,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("privy_manager")

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
app = Flask(__name__, template_folder=_TEMPLATE_DIR)

# 全局状态
task_status = {"is_running": False, "logs": [], "results": []}
task_lock = threading.Lock()
stop_event = threading.Event()

# --- JWT 辅助工具 ---
def get_jwt_expiry(token: str) -> Optional[int]:
    try:
        payload_b64 = token.split('.')[1]
        payload_b64 += '=' * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.b64decode(payload_b64))
        return payload.get("exp")
    except: return None

# --- 数据库管理 ---
class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'pending',
                    credits TEXT,
                    access_token TEXT,
                    identity_token TEXT,
                    refresh_token TEXT,
                    privy_access_token TEXT,
                    wallet_address TEXT,
                    created_at TEXT NOT NULL,
                    expires_at INTEGER
                )
            """)
            try: cursor.execute("ALTER TABLE accounts ADD COLUMN expires_at INTEGER")
            except: pass
            cursor.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.commit()

    def get_config(self, key: str, default: str = "") -> str:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
            res = cursor.fetchone()
            return res[0] if res else default

    def set_config(self, key: str, value: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    def get_accounts(self, status: str = None) -> list:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM accounts WHERE status = ? ORDER BY id DESC", (status,))
            else:
                cursor.execute("SELECT * FROM accounts ORDER BY id DESC")
            return cursor.fetchall()

    def save_account(self, data: Dict[str, Any]):
        exp = get_jwt_expiry(data.get("identity_token", ""))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO accounts
                (email, status, credits, access_token, identity_token, refresh_token, privy_access_token, wallet_address, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["email"], data["status"], data.get("credits"), data.get("access_token"),
                data.get("identity_token"), data.get("refresh_token"), data.get("privy_access_token"),
                data.get("wallet_address"), datetime.now().isoformat(), exp
            ))
            conn.commit()

    def update_token(self, email: str, id_token: str, access_token: str, refresh_token: str = None):
        exp = get_jwt_expiry(id_token)
        with sqlite3.connect(self.db_path) as conn:
            if refresh_token is None:
                conn.execute("UPDATE accounts SET identity_token = ?, privy_access_token = ?, expires_at = ? WHERE email = ?", (id_token, access_token, exp, email))
            else:
                conn.execute("UPDATE accounts SET identity_token = ?, privy_access_token = ?, refresh_token = ?, expires_at = ? WHERE email = ?", (id_token, access_token, refresh_token, exp, email))
            conn.commit()

    def update_credits(self, email: str, credits: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE accounts SET credits = ? WHERE email = ?", (credits, email))
            conn.commit()

    def update_status(self, email: str, status: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE accounts SET status = ? WHERE email = ?", (status, email))
            conn.commit()

    def delete_account(self, email: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM accounts WHERE email = ?", (email,))

    def clear_accounts(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM accounts")

    def get_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM accounts")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM accounts WHERE status = 'success'")
            success = cursor.fetchone()[0]
            return {"total": total, "success": success}

db = Database()

def add_log(message: str):
    with task_lock:
        print(message)
        task_status["logs"].append(f"{datetime.now().strftime('%H:%M:%S')} {message}")
        if len(task_status["logs"]) > 500: task_status["logs"] = task_status["logs"][-500:]

FIRST_NAMES = [
    "alex", "ben", "chris", "david", "eric", "frank", "george", "henry", "jack", "james",
    "kevin", "leo", "mike", "nick", "oliver", "peter", "ryan", "sam", "tom", "will",
    "anna", "bella", "cindy", "diana", "emma", "fiona", "grace", "helen", "iris", "jenny",
    "kate", "lily", "mia", "nina", "olivia", "rose", "sara", "tina", "vivian", "zoe",
]


def generate_mailbox_local_part() -> str:
    name = random.choice(FIRST_NAMES)
    date_part = datetime.now().strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{name}_{date_part}_{suffix}"

# --- 业务逻辑 ---
def worker(email_idx: int, stop_event: threading.Event, domain: str = None):
    if stop_event.is_set(): return
    uid = generate_mailbox_local_part()
    try:
        add_log(f"开始注册账号 #{email_idx}")
        proxies = get_proxies()
        client = AnumaClient(mail_api_key=MAIL_API_KEY, proxies=proxies, mail_proxies=None)
        res = client.signup(mailbox_local_part=uid, domain=domain, progress=lambda msg: add_log(f"#{email_idx} {msg}"))
        db.save_account({
            "email": res["email"], "status": "success", "credits": str(res["credits"]["available_credits"]),
            "access_token": res["access_token"], "identity_token": res["identity_token"],
            "refresh_token": client.refresh_token, "privy_access_token": client.privy_access_token,
            "wallet_address": client.wallet_address
        })
        add_log(f"[+] {res['email']} 注册完成")
    except Exception as e: add_log(f"[!] 失败 #{email_idx}: {e}")

def run_task(total: int, concurrency: int, stop_event: threading.Event, domain: str = None):
    add_log(f"任务启动: 总数 {total}, 并发 {concurrency}")
    queue = Queue()
    for i in range(total): queue.put(i)
    def thread_worker():
        while not queue.empty() and not stop_event.is_set():
            try: idx = queue.get_nowait(); worker(idx, stop_event, domain); queue.task_done()
            except Empty: break
    threads = [threading.Thread(target=thread_worker) for _ in range(concurrency)]
    for t in threads: t.start()
    for t in threads: t.join()
    with task_lock: task_status["is_running"] = False
    add_log("任务已结束")

def token_refresher_loop():
    """后台巡检：自动续费令牌"""
    while True:
        try:
            accounts = db.get_accounts(status="success")
            now = int(time.time())
            add_log(f"[*] 后台续期巡检: {len(accounts)} 个账号")
            for acc in accounts:
                # 索引: 1:email, 5:identity, 6:refresh, 7:access, 10:expires_at
                email, id_token, ref_token, acc_token, exp = acc[1], acc[5], acc[6], acc[7], acc[10]
                if not exp: exp = get_jwt_expiry(id_token)
                if exp and (exp - now < 3600): # 剩余不足1小时
                    try:
                        client = AnumaClient(MAIL_API_KEY, proxies=get_proxies())
                        new_id = client.refresh_id_token(ref_token, acc_token)
                        db.update_token(email, new_id, client.privy_access_token, client.refresh_token)
                        add_log(f"[*] 后台自动续期成功: {email}")
                    except Exception as e:
                        add_log(f"[!] 后台自动续期失败 {email}: {e}")
        except: pass
        time.sleep(600)

# --- Flask 路由 ---
@app.route("/")
def index():
    stats = db.get_stats()
    raw_accs = db.get_accounts()
    accounts = []
    now = int(time.time())
    for acc in raw_accs:
        exp = acc[10]
        exp_str, exp_class = "", ""
        if exp:
            exp_str = datetime.fromtimestamp(exp).strftime('%m-%d %H:%M')
            diff = exp - now
            if diff < 3600: exp_class = "text-danger fw-bold"
            elif diff < 86400: exp_class = "text-warning"
            else: exp_class = "text-success"
        accounts.append({"email": acc[1], "status": acc[2], "credits": acc[3], "created_at": acc[9], "exp_str": exp_str, "exp_class": exp_class})

    domains = []
    try: domains = AnumaClient(MAIL_API_KEY, proxies=get_proxies()).get_domains()
    except: pass

    config = {
	        "total": db.get_config("total", str(DEFAULT_TOTAL)),
	        "concurrency": db.get_config("concurrency", str(DEFAULT_CONCURRENCY)),
	        "timeout": db.get_config("timeout", str(DEFAULT_TIMEOUT)),
	        "interval": db.get_config("interval", str(DEFAULT_INTERVAL)),
	        "domain": db.get_config("domain", DEFAULT_DOMAIN),
	        "domains": domains,
	    }
    return render_template("index.html", stats=stats, accounts=accounts, config=config, task_active=task_status["is_running"])

@app.route("/api/config", methods=["POST"])
def save_cfg():
    for k, v in request.json.items(): db.set_config(k, str(v))
    return jsonify({"success": True})

@app.route("/api/task/start", methods=["POST"])
def start_t():
    global stop_event
    if task_status["is_running"]: return jsonify({"success": False})
    data = request.json
    with task_lock:
        task_status["is_running"] = True
        task_status["logs"] = []
        stop_event = threading.Event()
    threading.Thread(target=run_task, args=(int(data.get("total", 10)), int(data.get("concurrency", 3)), stop_event, data.get("domain"))).start()
    return jsonify({"success": True})

@app.route("/api/task/stop", methods=["POST"])
def stop_t():
    stop_event.set()
    return jsonify({"success": True})

@app.route("/api/task/status")
def task_s(): return jsonify(task_status)

@app.route("/api/accounts/query-credits", methods=["POST"])
def query_c():
    emails = request.json.get("emails", [])
    results = []
    all_accs = {a[1]: a for a in db.get_accounts()}
    for email in emails:
        if email not in all_accs: continue
        acc = all_accs[email]
        try:
            client = AnumaClient(MAIL_API_KEY, proxies=get_proxies())
            client.identity_token = acc[5]
            try: bal = client.get_balance()
            except Exception as e:
                if "token" in str(e).lower():
                    new_id = client.refresh_id_token(acc[6], acc[7])
                    db.update_token(email, new_id, client.privy_access_token, client.refresh_token)
                    client.identity_token = new_id
                    bal = client.get_balance()
                else: raise e
            db.update_credits(email, str(bal["available_credits"]))
            results.append({"email": email, "success": True, "data": bal})
        except Exception as e: results.append({"email": email, "success": False, "error": str(e)})
    return jsonify({"success": True, "results": results})

@app.route("/api/accounts/refresh-token", methods=["POST"])
def manual_r():
    email = request.json.get("email")
    acc = {a[1]: a for a in db.get_accounts()}.get(email)
    if not acc: return jsonify({"success": False})
    try:
        client = AnumaClient(MAIL_API_KEY, proxies=get_proxies())
        new_id = client.refresh_id_token(acc[6], acc[7])
        db.update_token(email, new_id, client.privy_access_token, client.refresh_token)
        return jsonify({"success": True, "expires_at": get_jwt_expiry(new_id)})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route("/api/accounts", methods=["DELETE"])
def del_acc():
    db.delete_account(request.json.get("email"))
    return jsonify({"success": True})

@app.route("/api/accounts/clear", methods=["DELETE"])
def clear_accs():
    db.clear_accounts()
    return jsonify({"success": True})

if __name__ == "__main__":
    validate()
    threading.Thread(target=token_refresher_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=MANAGER_PORT)
