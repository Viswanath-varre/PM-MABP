
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, flash
from werkzeug.utils import secure_filename
import pandas as pd
from config import Config
from models import db, User, FileUpload

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    db.create_all()
    if not User.query.filter_by(phone="admin").first():
        admin = User(phone="admin", name="Administrator", designation="Admin", password="admin", role="admin")
        db.session.add(admin)
        db.session.commit()

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def do_login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    user = User.query.filter_by(phone=username, password=password).first()
    if not user:
        flash("Invalid username or password", "danger")
        return redirect(url_for("login"))
    session["user_phone"] = user.phone
    session["role"] = user.role
    session["name"] = user.name
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

def login_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_phone" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper

def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admins only", "warning")
            return redirect(url_for("dashboard"))
        return func(*args, **kwargs)
    return wrapper

@app.route("/dashboard")
@login_required
def dashboard():
    users_count = User.query.count()
    uploads_count = FileUpload.query.count()
    return render_template("dashboard.html", name=session.get("name"), role=session.get("role"), users=users_count, uploads=uploads_count)

@app.route("/users")
@login_required
@admin_required
def users_page():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("users.html", users=users)

@app.route("/users/create", methods=["POST"])
@login_required
@admin_required
def users_create():
    phone = request.form.get("phone","").strip()
    name = request.form.get("name","").strip()
    designation = request.form.get("designation","").strip()
    password = request.form.get("password","").strip()
    role = request.form.get("role","user").strip() or "user"
    if not phone or not name or not password:
        flash("Phone, Name, and Password are required.", "danger")
        return redirect(url_for("users_page"))
    if User.query.filter_by(phone=phone).first():
        flash("Phone already exists.", "warning")
        return redirect(url_for("users_page"))
    u = User(phone=phone, name=name, designation=designation, password=password, role=role)
    db.session.add(u)
    db.session.commit()
    flash("User created.", "success")
    return redirect(url_for("users_page"))

@app.route("/users/delete/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def users_delete(user_id):
    default_admin = User.query.filter_by(phone="admin").first()
    if default_admin and user_id == default_admin.id:
        flash("Cannot delete default admin.", "warning")
        return redirect(url_for("users_page"))
    User.query.filter_by(id=user_id).delete()
    db.session.commit()
    flash("User deleted.", "success")
    return redirect(url_for("users_page"))

@app.route("/users/update/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def users_update(user_id):
    u = User.query.get_or_404(user_id)
    u.name = request.form.get("name", u.name)
    u.designation = request.form.get("designation", u.designation)
    u.role = request.form.get("role", u.role)
    pw = request.form.get("password", "").strip()
    if pw:
        u.password = pw
    db.session.commit()
    flash("User updated.", "success")
    return redirect(url_for("users_page"))

def handle_category_page(category, template_name):
    @login_required
    def view_func():
        files = FileUpload.query.filter_by(category=category).order_by(FileUpload.uploaded_at.desc()).limit(10).all()
        preview_headers, preview_rows, preview_error = [], [], None
        if files:
            latest = files[0]
            path = os.path.join(app.config["UPLOAD_FOLDER"], latest.saved_as)
            try:
                if latest.filename.lower().endswith(".csv"):
                    df = pd.read_csv(path)
                else:
                    df = pd.read_excel(path)
                preview_headers = list(df.columns)[:12]
                preview_rows = df.head(20).values.tolist()
            except Exception as e:
                preview_error = str(e)
        return render_template(template_name, files=files, preview_headers=preview_headers, preview_rows=preview_rows, preview_error=preview_error, category=category)
    return view_func

def handle_category_upload(category):
    @login_required
    def upload_func():
        if "file" not in request.files:
            flash("No file part", "danger")
            return redirect(request.referrer or url_for("dashboard"))
        f = request.files["file"]
        if f.filename == "":
            flash("No selected file", "warning")
            return redirect(request.referrer or url_for("dashboard"))
        if not allowed_file(f.filename):
            flash("Only CSV/XLSX/XLS allowed", "danger")
            return redirect(request.referrer or url_for("dashboard"))

        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        filename = secure_filename(f.filename)
        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        saved_as = f"{category}__{stamp}__{filename}"
        path = os.path.join(app.config["UPLOAD_FOLDER"], saved_as)
        f.save(path)

        meta = FileUpload(
            category=category,
            filename=filename,
            saved_as=saved_as,
            size_bytes=os.path.getsize(path),
            uploaded_by=session.get("user_phone") or "unknown"
        )
        db.session.add(meta)
        db.session.commit()

        flash("File uploaded.", "success")
        return redirect(request.referrer or url_for("dashboard"))
    return upload_func

app.add_url_rule("/asset-master", view_func=handle_category_page("asset_master", "asset_master.html"), endpoint="asset_master")
app.add_url_rule("/maintenance", view_func=handle_category_page("maintenance", "maintenance.html"), endpoint="maintenance")
app.add_url_rule("/running-status", view_func=handle_category_page("running_status", "running_status.html"), endpoint="running_status")
app.add_url_rule("/uauc", view_func=handle_category_page("uauc", "uauc.html"), endpoint="uauc")
app.add_url_rule("/hsd", view_func=handle_category_page("hsd", "hsd.html"), endpoint="hsd")
app.add_url_rule("/emfc", view_func=handle_category_page("emfc", "emfc.html"), endpoint="emfc")
app.add_url_rule("/gps-log", view_func=handle_category_page("gpslog", "gps_log.html"), endpoint="gps_log")

app.add_url_rule("/upload/asset-master", methods=["POST"], view_func=handle_category_upload("asset_master"), endpoint="handle_category_upload_asset_master")
app.add_url_rule("/upload/maintenance", methods=["POST"], view_func=handle_category_upload("maintenance"), endpoint="handle_category_upload_maintenance")
app.add_url_rule("/upload/running-status", methods=["POST"], view_func=handle_category_upload("running_status"), endpoint="handle_category_upload_running_status")
app.add_url_rule("/upload/uauc", methods=["POST"], view_func=handle_category_upload("uauc"), endpoint="handle_category_upload_uauc")
app.add_url_rule("/upload/hsd", methods=["POST"], view_func=handle_category_upload("hsd"), endpoint="handle_category_upload_hsd")
app.add_url_rule("/upload/emfc", methods=["POST"], view_func=handle_category_upload("emfc"), endpoint="handle_category_upload_emfc")
app.add_url_rule("/upload/gps-log", methods=["POST"], view_func=handle_category_upload("gpslog"), endpoint="handle_category_upload_gpslog")

@app.route("/uploads/<path:name>")
@login_required
def download_upload(name):
    return send_from_directory(app.config["UPLOAD_FOLDER"], name, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
