import os, subprocess, threading, uuid, time, json, re, hashlib, secrets, queue
from pathlib import Path
from flask import (Flask, request, jsonify, send_from_directory,
                   send_file, abort, Response)
from flask_cors import CORS

app = Flask(__name__, static_folder="static", static_url_path="/")
app.secret_key = secrets.token_hex(32)
CORS(app, supports_credentials=True)

# dget 没有 -d 参数，下载到工作目录，挂载 WORK_DIR 即可
WORK_DIR  = os.environ.get("WORK_DIR", "./downloads")
DATA_DIR  = os.environ.get("DATA_DIR", "./data")
PORT      = int(os.environ.get("PORT", 8080))
DGET_USER = os.environ.get("DGET_USER", "admin")
DGET_PASS = os.environ.get("DGET_PASS", "admin123")

Path(WORK_DIR).mkdir(parents=True, exist_ok=True)
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

TASKS_FILE = Path(DATA_DIR) / "tasks.json"

# ── task store ────────────────────────────────────────────────────────────────
tasks = {}
tasks_lock = threading.Lock()

def load_tasks():
    if TASKS_FILE.exists():
        try:
            with open(TASKS_FILE) as f:
                data = json.load(f)
            with tasks_lock:
                tasks.update(data)
        except Exception:
            pass

def save_tasks():
    with tasks_lock:
        snapshot = dict(tasks)
    try:
        with open(TASKS_FILE, "w") as f:
            json.dump(snapshot, f, ensure_ascii=False)
    except Exception:
        pass

load_tasks()

# ── SSE subscribers ───────────────────────────────────────────────────────────
subscribers = {}
subs_lock = threading.Lock()

def publish(task_id, line):
    with subs_lock:
        qs = list(subscribers.get(task_id, []))
    for q in qs:
        try:
            q.put_nowait(line)
        except queue.Full:
            pass

# ── helpers ───────────────────────────────────────────────────────────────────
def safe_name(name):
    return bool(name) and ".." not in name and "/" not in name

def humanize(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def hash_pass(p):
    return hashlib.sha256(p.encode()).hexdigest()

PASS_HASH = hash_pass(DGET_PASS)
AUTH_TOKENS = set()
AUTH_LOCK = threading.Lock()

def check_token(token):
    if not token:
        return False
    with AUTH_LOCK:
        return token in AUTH_TOKENS

def require_login(f):
    from functools import wraps
    @wraps(f)
    def inner(*a, **kw):
        token = (request.cookies.get("dget_token") or
                 request.headers.get("X-Auth-Token"))
        if not check_token(token):
            abort(401)
        return f(*a, **kw)
    return inner

# ── background downloader ─────────────────────────────────────────────────────
def run_download(task_id, image, arch):
    def log(line):
        with tasks_lock:
            tasks[task_id]["logs"].append(line)
        publish(task_id, line)

    with tasks_lock:
        tasks[task_id]["status"] = "running"
    save_tasks()

    # 正确用法：dget [-arch linux/amd64] <image>
    # 在 WORK_DIR 下执行，产物就落在该目录
    args = ["dget"]
    if arch:
        args += ["-arch", arch]
    args.append(image)

    cmd_str = " ".join(args)
    log(f"[CMD] {cmd_str}  (工作目录: {WORK_DIR})")

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=WORK_DIR,      # 关键：切换到挂载目录，产物直接落这里
        )
        for line in proc.stdout:
            log(line.rstrip())
        proc.wait()
        status = "done" if proc.returncode == 0 else "error"
        if proc.returncode != 0:
            log(f"[ERROR] dget 退出码 {proc.returncode}")
        else:
            log("[OK] 下载完成！")
    except FileNotFoundError:
        log("[ERROR] dget 未找到，请确认 /usr/local/bin/dget 存在且有执行权限。")
        status = "error"
    except Exception as e:
        log(f"[ERROR] {e}")
        status = "error"

    with tasks_lock:
        tasks[task_id]["status"] = status
        tasks[task_id]["finished_at"] = time.time()
    publish(task_id, f"__STATUS__{status}")
    save_tasks()

# ── auth ──────────────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if username != DGET_USER or hash_pass(password) != PASS_HASH:
        return jsonify({"error": "用户名或密码错误"}), 401
    token = secrets.token_hex(24)
    with AUTH_LOCK:
        AUTH_TOKENS.add(token)
    resp = jsonify({"status": "ok", "token": token, "username": username})
    resp.set_cookie("dget_token", token, httponly=True, samesite="Lax")
    return resp

@app.route("/api/logout", methods=["POST"])
def logout():
    token = request.cookies.get("dget_token") or request.headers.get("X-Auth-Token")
    if token:
        with AUTH_LOCK:
            AUTH_TOKENS.discard(token)
    resp = jsonify({"status": "ok"})
    resp.delete_cookie("dget_token")
    return resp

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

# ── download task ─────────────────────────────────────────────────────────────
@app.route("/api/download", methods=["POST"])
@require_login
def start_download():
    body = request.get_json(silent=True) or {}
    image = (body.get("image") or "").strip()
    arch  = (body.get("arch") or "").strip() or None
    if not image:
        return jsonify({"error": "image 不能为空"}), 400
    # 允许包含 . / : - _ @ 等字符（支持第三方 registry 地址）
    if not re.match(r"^[\w.\-/:@]+$", image):
        return jsonify({"error": "镜像名包含非法字符"}), 400
    task_id = uuid.uuid4().hex[:8]
    with tasks_lock:
        tasks[task_id] = {
            "id": task_id, "image": image, "arch": arch,
            "status": "pending", "logs": [],
            "created_at": time.time(), "finished_at": None,
        }
    save_tasks()
    threading.Thread(target=run_download, args=(task_id, image, arch), daemon=True).start()
    return jsonify({"task_id": task_id})

# ── task CRUD ─────────────────────────────────────────────────────────────────
@app.route("/api/tasks")
@require_login
def list_tasks():
    with tasks_lock:
        result = list(tasks.values())
    result.sort(key=lambda t: t["created_at"], reverse=True)
    return jsonify(result)

@app.route("/api/tasks/<task_id>")
@require_login
def get_task(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "not found"}), 404
    return jsonify(task)

@app.route("/api/tasks/<task_id>/delete", methods=["POST", "DELETE"])
@require_login
def delete_task(task_id):
    with tasks_lock:
        if task_id not in tasks:
            return jsonify({"error": "not found"}), 404
        del tasks[task_id]
    save_tasks()
    return jsonify({"status": "deleted"})

# ── SSE stream ────────────────────────────────────────────────────────────────
@app.route("/api/tasks/<task_id>/stream")
def stream_task(task_id):
    token = (request.args.get("token") or
             request.cookies.get("dget_token") or
             request.headers.get("X-Auth-Token"))
    if not check_token(token):
        abort(401)
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        abort(404)
    with tasks_lock:
        existing   = list(task.get("logs", []))
        cur_status = task["status"]

    q = queue.Queue(maxsize=512)
    with subs_lock:
        subscribers.setdefault(task_id, []).append(q)

    def generate():
        for line in existing:
            payload = json.dumps({"line": line}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
        if cur_status in ("done", "error"):
            yield f"data: {json.dumps({'status': cur_status})}\n\n"
            return
        while True:
            try:
                msg = q.get(timeout=25)
                if msg.startswith("__STATUS__"):
                    yield f"data: {json.dumps({'status': msg[10:]})}\n\n"
                    break
                else:
                    payload = json.dumps({"line": msg}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
            except queue.Empty:
                yield "data: {\"ping\":1}\n\n"
        with subs_lock:
            try:
                subscribers[task_id].remove(q)
            except ValueError:
                pass

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── files ─────────────────────────────────────────────────────────────────────
@app.route("/api/files")
@require_login
def list_files():
    files = []
    base = Path(WORK_DIR)
    # 递归扫描，dget 产物在 tmp_<author>/ 子目录下
    for p in base.rglob("*.tar.gz"):
        if p.is_file():
            stat = p.stat()
            rel = p.relative_to(base)
            files.append({
                "name": str(rel),          # 相对路径，如 tmp_library/nginx_latest.tar.gz
                "basename": p.name,
                "subdir": str(rel.parent) if str(rel.parent) != "." else "",
                "size": stat.st_size,
                "size_human": humanize(stat.st_size),
                "mod_time": stat.st_mtime,
            })
    files.sort(key=lambda f: f["mod_time"], reverse=True)
    return jsonify(files)

@app.route("/api/files/download")
@require_login
def download_file():
    name = request.args.get("name", "")
    # 防路径穿越
    try:
        path = (Path(WORK_DIR) / name).resolve()
        path.relative_to(Path(WORK_DIR).resolve())
    except (ValueError, Exception):
        abort(400)
    if not path.exists() or not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name)

@app.route("/api/files/delete", methods=["POST", "DELETE"])
@require_login
def delete_file():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "文件名不能为空"}), 400
    try:
        path = (Path(WORK_DIR) / name).resolve()
        path.relative_to(Path(WORK_DIR).resolve())
    except (ValueError, Exception):
        return jsonify({"error": "非法路径"}), 400
    if not path.exists():
        return jsonify({"error": "文件不存在"}), 404
    path.unlink()
    # 若子目录为空则删除
    parent = path.parent
    if parent != Path(WORK_DIR).resolve() and not any(parent.iterdir()):
        parent.rmdir()
    return jsonify({"status": "deleted"})

if __name__ == "__main__":
    print(f"[dget-web] 启动 :{PORT}  工作目录:{WORK_DIR}  数据目录:{DATA_DIR}")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
