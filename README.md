# Internship Task 1: Web Service and Database in Docker

Deployment of the video recording web service and database in separate Docker containers using Docker Compose:
- **`web`**: Apache 2.4 web server serving the Flask application via `mod_wsgi` on port `8000:80`.
- **`db`**: PostgreSQL 16 with health check (`pg_isready`) and volume-backed storage.

---

## Architecture

```text
+-----------------------------------------------------------------------+
|                            Docker Compose                             |
|                                                                       |
|  +---------------------------+         +---------------------------+  |
|  |       web container       |         |       db container        |  |
|  |  (Apache 2.4 + mod_wsgi)  |         |      (PostgreSQL 16)      |  |
|  |                           |         |                           |  |
|  |  - Python WSGI (Flask)    |  SQL    |  - Port 5432 (internal)   |  |
|  |  - Port 80 -> Host 8000   |-------->|  - Healthcheck pg_isready |  |
|  |  - Direct /media serving  |         |  - videos table (upsert)  |  |
|  +---------------------------+         +---------------------------+  |
|                |                                     |                |
|  Volume:       v                                     v      Volume:   |
|  uploads -> /app/uploads                       /var/lib/postgresql/data
|                                                (db_data)              |
+-----------------------------------------------------------------------+
```

### Components

1. **`web` service**:
   - Debian Bookworm Slim with native `apache2` and `libapache2-mod-wsgi-py3`.
   - Python dependencies installed via `requirements.txt` (`Flask`, `psycopg2-binary`).
   - Apache virtual host with `WSGIDaemonProcess` and static `Alias /media /app/uploads`.
   - Depends on `db` via `condition: service_healthy`.
2. **`db` service**:
   - Official image `postgres:16`.
   - Health check: `pg_isready -U ${DB_USER:-video_user} -d ${DB_NAME:-videos}`.
   - Dedicated named volume `db_data` for PostgreSQL data directory.
3. **Data persistence**:
   - Database state stored in `db_data`.
   - Video files stored in `uploads`.
   - Named volumes preserve both database rows and uploaded files across `docker compose down` and `docker compose up`.

---

## Directory Structure

```text
internship_task1/
├── Dockerfile                  # Apache + mod_wsgi + Flask container definition
├── docker-compose.yml          # Multi-container orchestration (web + db)
├── apache.conf                 # Apache VirtualHost & WSGI daemon configuration
├── entrypoint.sh               # Runtime configuration and Apache startup script
├── web_service.wsgi            # WSGI entry point
├── web_service.py              # Flask service with PostgreSQL backend
├── requirements.txt            # Server dependencies (Flask, psycopg2-binary)
├── requirements-client.txt     # Client dependencies (requests, playwright)
├── video_client.py             # Client API: UploadVideo, GetVideoURL
├── capture_video.py            # Automation recorder CLI
├── qscript.py                  # Browser recording scenario
├── input.csv                   # Input company dataset
├── .env.example                # Environment variables template
├── .gitattributes              # LF line-ending enforcement for shell scripts
├── .gitignore                  # Git ignore rules
├── README.md                   # Documentation
├── tests/                      # Unit test suite
│   ├── test_service.py         # Tests for Flask service and PostgreSQL logic
│   └── test_client.py          # Tests for client API
└── video/                      # Recorded video samples (.webm)
    ├── Acme Berlin Tech.webm
    └── Bavaria Soft Solutions.webm
```

---

## Quick Start

### 1. Build and Start Containers

```bash
docker compose up --build
```

To run in the background:
```bash
docker compose up --build -d
```

Startup sequence:
1. `db` starts and initializes PostgreSQL 16.
2. Compose monitors database health via `pg_isready`.
3. `web` starts after `db` becomes healthy, verifies database connectivity, and binds to `http://127.0.0.1:8000`.

### 2. Check Service Status & Logs

```bash
docker compose ps
docker compose logs -f web
docker compose logs -f db
```

---

## API Endpoints

The web service is available on `http://127.0.0.1:8000`:

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Service status and endpoint list |
| `GET` | `/health` | Connectivity check to PostgreSQL (returns 200 or 503) |
| `POST` | `/upload` | Multipart upload (`file`, `company_name`), returns video URL |
| `GET` | `/get_video_url?company_name=<name>` | Retrieves video URL for company (200 or 404) |
| `GET` | `/media/<filename>` | Serves uploaded video directly via Apache Alias |
| `GET` | `/videos` | Returns all recorded company video entries |

### Examples

```bash
# Health check
curl http://127.0.0.1:8000/health

# List video records
curl http://127.0.0.1:8000/videos

# Retrieve video URL by company name
curl "http://127.0.0.1:8000/get_video_url?company_name=Acme%20Berlin%20Tech"
```

---

## Running the Client & Video Recorder

To run the recorder on the host machine:

```bash
pip install -r requirements-client.txt
playwright install chromium

# Record from input.csv, upload to server, and preview each video for 5 seconds
python capture_video.py --server http://127.0.0.1:8000 --view-seconds 5

# Interactive preview (press Enter to proceed to the next item)
python capture_video.py --server http://127.0.0.1:8000 --view-seconds 0
```

---

## Testing Persistence

1. Upload a video file via `capture_video.py` or curl.
2. Stop the containers:
   ```bash
   docker compose down
   ```
3. Restart containers without `-v`:
   ```bash
   docker compose up -d
   ```
4. Query the stored data:
   ```bash
   curl http://127.0.0.1:8000/videos
   curl "http://127.0.0.1:8000/get_video_url?company_name=Acme%20Berlin%20Tech"
   ```
   Both the PostgreSQL records in `db_data` and the media files in `uploads` remain available.

---

## Running Tests

Run unit tests inside the `web` container:
```bash
docker compose exec web python -m unittest discover -s tests -v
```

Or run locally on the host:
```bash
python -m unittest discover -s tests -v
```

---

## Configuration

The stack can be customized using environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `db` | PostgreSQL service host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `videos` | Database name |
| `DB_USER` | `video_user` | Database username |
| `DB_PASSWORD` | `video_pass` | Database password |
| `DB_CONNECT_TIMEOUT` | `10` | Connection timeout in seconds |
| `UPLOADS_DIR` | `/app/uploads` | Storage directory for video files |
