import os
import re
import sys
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, send_from_directory, g, has_request_context
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.environ.get("UPLOADS_DIR", os.path.join(BASE_DIR, "uploads"))

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


def get_db_config():
    """Reads database connection settings from environment variables."""
    host = os.environ.get("DB_HOST", "db")
    port = int(os.environ.get("DB_PORT", 5432))
    dbname = os.environ.get("DB_NAME", "videos")
    user = os.environ.get("DB_USER", "video_user")
    password = os.environ.get("DB_PASSWORD", "video_pass")
    connect_timeout = int(os.environ.get("DB_CONNECT_TIMEOUT", 10))

    try:
        if has_request_context():
            host = request.environ.get("DB_HOST") or host
            port = int(request.environ.get("DB_PORT") or port)
            dbname = request.environ.get("DB_NAME") or dbname
            user = request.environ.get("DB_USER") or user
            password = request.environ.get("DB_PASSWORD") or password
    except Exception:
        pass

    return {
        "host": host,
        "port": port,
        "dbname": dbname,
        "user": user,
        "password": password,
        "connect_timeout": connect_timeout,
    }


def safe_company_filename(company_name: str, original_filename: str = "") -> str:
    """Generates a clean and safe filename for disk storage."""
    ext = os.path.splitext(original_filename)[1] if original_filename else ".webm"
    if not ext:
        ext = ".webm"
    safe = re.sub(r'[^\w\d\-_]', '_', company_name.strip()).strip('_')
    if not safe:
        safe = "video"
    return f"{safe}{ext}"


def get_db():
    """Provides a per-request PostgreSQL database connection."""
    if "db" not in g:
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        g.db = psycopg2.connect(**get_db_config())
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    """Closes the database connection at the end of each request."""
    db = g.pop("db", None)
    if db is not None and not db.closed:
        if exception is not None:
            try:
                db.rollback()
            except Exception:
                pass
        db.close()


def wait_for_db(max_retries: int = 30, retry_interval: float = 2.0) -> bool:
    """Waits for PostgreSQL to be ready and initializes the schema."""
    cfg = get_db_config()
    sys.stdout.write(f"Connecting to PostgreSQL at {cfg['host']}:{cfg['port']}/{cfg['dbname']}...\n")
    sys.stdout.flush()

    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(**cfg)
            conn.close()
            sys.stdout.write(f"PostgreSQL connection established on attempt {attempt}.\n")
            sys.stdout.flush()
            init_db()
            return True
        except psycopg2.OperationalError as err:
            sys.stdout.write(f"Waiting for database (attempt {attempt}/{max_retries}): {err}\n")
            sys.stdout.flush()
            time.sleep(retry_interval)

    sys.stderr.write("Could not establish database connection after multiple retries.\n")
    sys.stderr.flush()
    return False


def init_db():
    """Ensures uploads directory and videos table schema exist."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id SERIAL PRIMARY KEY,
                    company_name TEXT NOT NULL UNIQUE,
                    file_path TEXT NOT NULL,
                    video_url TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
            """)
        conn.commit()
    finally:
        conn.close()


@app.route("/", methods=["GET"])
def index():
    """Service status and endpoint index for container inspection."""
    return jsonify({
        "service": "Video Recording Web Service",
        "status": "running",
        "endpoints": {
            "upload": "POST /upload",
            "get_video_url": "GET /get_video_url?company_name=<name>",
            "media": "GET /media/<filename>",
            "videos": "GET /videos",
            "health": "GET /health"
        }
    }), 200


@app.route("/health", methods=["GET"])
def health_check():
    """Healthcheck endpoint for orchestrators and monitoring."""
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT 1;")
        return jsonify({"status": "ok", "database": "connected"}), 200
    except Exception as err:
        return jsonify({"status": "error", "database": str(err)}), 500


@app.route("/upload", methods=["POST"])
def upload_video():
    """Uploads a video file and upserts record in PostgreSQL."""
    if "file" not in request.files:
        return jsonify({"error": "Missing 'file' field in multipart form"}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return jsonify({"error": "Empty filename provided"}), 400

    company_name = request.form.get("company_name", "").strip()
    if not company_name:
        return jsonify({"error": "Missing 'company_name' parameter"}), 400

    filename = safe_company_filename(company_name, uploaded_file.filename)
    dest_path = os.path.join(UPLOADS_DIR, filename)
    uploaded_file.save(dest_path)

    abs_file_path = os.path.abspath(dest_path)
    video_url = f"{request.host_url.rstrip('/')}/media/{filename}"

    db = get_db()
    with db.cursor() as cur:
        cur.execute("""
            INSERT INTO videos (company_name, file_path, video_url, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            ON CONFLICT (company_name) DO UPDATE SET
                file_path = EXCLUDED.file_path,
                video_url = EXCLUDED.video_url,
                updated_at = NOW();
        """, (company_name, abs_file_path, video_url))
    db.commit()

    return jsonify({
        "company_name": company_name,
        "video_url": video_url
    }), 200


@app.route("/get_video_url", methods=["GET"])
def get_video_url():
    """Retrieves the public video URL for a given company name."""
    company_name = request.args.get("company_name", "").strip()
    if not company_name:
        return jsonify({"error": "Missing 'company_name' query parameter"}), 400

    db = get_db()
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT company_name, video_url FROM videos WHERE company_name = %s",
            (company_name,)
        )
        row = cur.fetchone()

    if row is None:
        return jsonify({"error": f"No video found for company '{company_name}'"}), 404

    return jsonify({
        "company_name": row["company_name"],
        "video_url": row["video_url"]
    }), 200


@app.route("/media/<path:filename>", methods=["GET"])
def serve_media(filename):
    """Serves the uploaded video file directly for in-browser playback."""
    return send_from_directory(UPLOADS_DIR, filename, mimetype="video/webm")


@app.route("/videos", methods=["GET"])
def list_videos():
    """Lists all stored video records in JSON format."""
    db = get_db()
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, company_name, file_path, video_url,
                   to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') as created_at,
                   to_char(updated_at, 'YYYY-MM-DD HH24:MI:SS') as updated_at
            FROM videos ORDER BY id ASC
        """)
        rows = cur.fetchall()
    return jsonify([dict(row) for row in rows]), 200


if __name__ == "__main__":
    wait_for_db()
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 8000))
    app.run(host=host, port=port, threaded=True)
