import os
import json
import secrets
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import requests
import pandas as pd

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")  # server-side only
FLASK_SECRET = os.getenv("FLASK_SECRET") or secrets.token_hex(16)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = FLASK_SECRET

UPLOAD_FOLDER = "uploads"
ALLOWED_EXT = {"xls","xlsx","csv"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def sb_headers(admin=False):
    key = SUPABASE_SERVICE_ROLE if admin else SUPABASE_ANON_KEY
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def sb_table_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"

def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXT

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/admin")
def admin_page():
    if session.get("role") != "admin":
        return redirect(url_for("home"))
    return render_template("admin.html", username=session.get("username"))

@app.route("/user")
def user_page():
    if session.get("username") is None:
        return redirect(url_for("home"))
    return render_template("user.html", username=session.get("username"))

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    # Bootstrap default admin/admin on first run if not exists
    try:
        r = requests.get(sb_table_url("users"), headers=sb_headers(), params={"select":"id"})
        r.raise_for_status()
        if isinstance(r.json(), list) and len(r.json()) == 0:
            payload = [{"username":"admin","password":"admin","role":"admin","permissions":["all"]}]
            rc = requests.post(sb_table_url("users"), headers=sb_headers(admin=True), data=json.dumps(payload))
            rc.raise_for_status()
    except Exception:
        pass

    try:
        params = {"select":"id,username,password,role,permissions","username":"eq." + username}
        resp = requests.get(sb_table_url("users"), headers=sb_headers(), params=params)
        if resp.status_code != 200:
            return jsonify({"ok":False, "error":"Auth service error"}), 500
        rows = resp.json()
        if not rows or rows[0].get("password") != password:
            return jsonify({"ok":False, "error":"Invalid credentials"}), 401
        u = rows[0]
        session["username"] = u["username"]
        session["role"] = u.get("role","user")
        session["permissions"] = u.get("permissions") or []
        return jsonify({"ok":True, "role":session["role"]})
    except Exception as e:
        return jsonify({"ok":False, "error":str(e)}), 500

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/api/admin/create_user", methods=["POST"])
def create_user():
    if session.get("role") != "admin":
        return jsonify({"ok":False,"error":"Not authorized"}), 403
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    role = data.get("role") or "user"
    permissions = data.get("permissions") or []
    if not username or not password:
        return jsonify({"ok":False,"error":"Username and password required"}), 400
    try:
        payload = [{"username": username,"password": password,"role": role,"permissions": permissions}]
        r = requests.post(sb_table_url("users"), headers=sb_headers(admin=True), data=json.dumps(payload))
        if r.status_code not in (200,201):
            return jsonify({"ok":False,"error":r.text}), 400
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 500

@app.route("/api/admin/list_users")
def list_users():
    if session.get("role") != "admin":
        return jsonify({"ok":False,"error":"Not authorized"}), 403
    r = requests.get(sb_table_url("users"), headers=sb_headers(), params={"select":"id,username,role,permissions"})
    if r.status_code != 200:
        return jsonify({"ok":False,"error":r.text}), 500
    return jsonify({"ok":True, "users": r.json()})

@app.route("/api/admin/upload/<slot>", methods=["POST"])
def upload_file(slot):
    if session.get("role") != "admin":
        return jsonify({"ok":False,"error":"Not authorized"}), 403
    if "file" not in request.files:
        return jsonify({"ok":False,"error":"No file"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"ok":False,"error":"Empty filename"}), 400
    if not allowed_file(f.filename):
        return jsonify({"ok":False,"error":"Only .xls, .xlsx, .csv allowed"}), 400

    filename = secure_filename(f.filename)
    save_path = os.path.join(UPLOAD_FOLDER, f"{slot}__{filename}")
    f.save(save_path)

    meta = {"slot": slot,"filename": filename,"saved_as": os.path.basename(save_path),
            "size_bytes": os.path.getsize(save_path),"uploaded_by": session.get("username"),
            "uploaded_at": datetime.utcnow().isoformat() + "Z"}
    try:
        r = requests.post(sb_table_url("file_uploads"), headers=sb_headers(admin=True), data=json.dumps([meta]))
        if r.status_code not in (200,201):
            return jsonify({"ok":True,"warning":"Saved file locally but failed to record in DB","db_error":r.text})
    except Exception as e:
        return jsonify({"ok":True,"warning":"Saved file locally; DB record error","db_error":str(e)})
    return jsonify({"ok":True,"file":meta})

@app.route("/uploads/<path:name>")
def dl(name):
    return send_from_directory(UPLOAD_FOLDER, name, as_attachment=True)

@app.route("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()+"Z"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)