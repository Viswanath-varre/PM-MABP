
import os
class Config:
    # Supabase Postgres connection string (password URL-encoded)
    SQLALCHEMY_DATABASE_URI = (
        "postgresql+psycopg2://postgres:Viswanath%40%23358@"
        "db.ywmeqbjdhkcnjfxjbnpb.supabase.co:5432/postgres"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("FLASK_SECRET", "super-secret-key")
    MAX_CONTENT_LENGTH = 128 * 1024 * 1024
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
    ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}
