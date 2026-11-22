import hashlib
import os
import re
from flask import Flask, g, jsonify, request, send_from_directory, has_request_context
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALLOWED_EXTENSIONS = {".webm", ".mp4"}

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


def get_uploads_dir() -> str:
    env = request.environ if has_request_context() else os.environ
    return env.get("UPLOADS_DIR", os.environ.get("UPLOADS_DIR", os.path.join(BASE_DIR, "uploads")))


def get_db_config() -> dict:
    env = request.environ if has_request_context() else os.environ
    return {
        "host": env.get("DB_HOST", os.environ.get("DB_HOST", "db")),
        "port": int(env.get("DB_PORT", os.environ.get("DB_PORT", "5432"))),
        "dbname": env.get("DB_NAME", os.environ.get("DB_NAME", "videos")),
        "user": env.get("DB_USER", os.environ.get("DB_USER", "video_user")),
        "password": env.get("DB_PASSWORD", os.environ.get("DB_PASSWORD", "video_pass")),
        "connect_timeout": int(env.get("DB_CONNECT_TIMEOUT", os.environ.get("DB_CONNECT_TIMEOUT", "10"))),
    }


def build_safe_filename(company_name: str, original_filename: str) -> str:
    ext = os.path.splitext(original_filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported video format. Allowed: .webm, .mp4")

    slug = re.sub(r"[^\w\-]+", "_", company_name.strip(), flags=re.UNICODE).strip("_")
    if not slug:
        slug = "company"

    digest = hashlib.sha256(company_name.strip().encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{digest}{ext}"


def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(**get_db_config())
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None and not conn.closed:
        if error is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        conn.close()


def init_db() -> None:
    uploads_dir = get_uploads_dir()
    os.makedirs(uploads_dir, exist_ok=True)

    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS videos (
                    id SERIAL PRIMARY KEY,
                    company_name TEXT NOT NULL UNIQUE,
                    file_path TEXT NOT NULL,
                    video_url TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()
    finally:
        conn.close()


@app.get("/")
def index():
    return jsonify(
        {
            "service": "video-service",
            "status": "ok",
            "endpoints": [
                "POST /upload",
                "GET /get_video_url?company_name=<name>",
                "GET /media/<filename>",
                "GET /videos",
                "GET /health",
            ],
        }
    ), 200


@app.get("/health")
def health():
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        return jsonify({"status": "ok", "db": "ok"}), 200
    except Exception as exc:
        app.logger.error("Health check DB failure: %s", exc)
        return jsonify({"status": "error", "db": "unavailable"}), 503


@app.post("/upload")
def upload():
    if "file" not in request.files:
        return jsonify({"error": "Missing 'file' field"}), 400

    upload_file = request.files["file"]
    if not upload_file or not upload_file.filename:
        return jsonify({"error": "Missing filename"}), 400

    company_name = request.form.get("company_name", "").strip()
    if not company_name:
        return jsonify({"error": "Missing 'company_name' field"}), 400

    try:
        filename = build_safe_filename(company_name, upload_file.filename)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    uploads_dir = get_uploads_dir()
    os.makedirs(uploads_dir, exist_ok=True)
    dest_path = os.path.abspath(os.path.join(uploads_dir, filename))
    video_url = f"{request.host_url.rstrip('/')}/media/{filename}"

    upload_file.save(dest_path)

    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO videos (company_name, file_path, video_url, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                ON CONFLICT (company_name) DO UPDATE SET
                    file_path = EXCLUDED.file_path,
                    video_url = EXCLUDED.video_url,
                    updated_at = NOW();
                """,
                (company_name, dest_path, video_url),
            )
        conn.commit()
    except Exception as exc:
        app.logger.error("Failed to save video metadata for %s: %s", company_name, exc)
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except OSError:
                pass
        return jsonify({"error": "Database error while saving video metadata"}), 500

    return jsonify({"company_name": company_name, "video_url": video_url}), 200


@app.get("/get_video_url")
def get_video_url():
    company_name = request.args.get("company_name", "").strip()
    if not company_name:
        return jsonify({"error": "Missing 'company_name' query parameter"}), 400

    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT company_name, video_url FROM videos WHERE company_name = %s;",
            (company_name,),
        )
        row = cur.fetchone()

    if row is None:
        return jsonify({"error": "Video not found"}), 404

    return jsonify({"company_name": row["company_name"], "video_url": row["video_url"]}), 200


@app.get("/media/<path:filename>")
def media(filename):
    return send_from_directory(get_uploads_dir(), filename)


@app.get("/videos")
def list_videos():
    conn = get_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                id,
                company_name,
                file_path,
                video_url,
                to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
                to_char(updated_at, 'YYYY-MM-DD HH24:MI:SS') AS updated_at
            FROM videos
            ORDER BY id ASC;
            """
        )
        rows = cur.fetchall()

    return jsonify([dict(row) for row in rows]), 200


if __name__ == "__main__":
    init_db()
    app.run(
        host=os.environ.get("FLASK_HOST", "0.0.0.0"),
        port=int(os.environ.get("FLASK_PORT", "8000")),
        threaded=True,
    )
