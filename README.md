# Internship Task 1: Web Service and Database in Docker

Containerized deployment of the video recording web service and database layer using Docker Compose. The solution separates the application into two dedicated containers: an Apache web server running the Flask application via `mod_wsgi`, and an official PostgreSQL 16 database container with automated health checks, data persistence, and volume management.

---

## Architecture Overview

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

### Key Components

1. **`web` Service**:
   - Base: Debian Bookworm Slim with native `apache2` and `libapache2-mod-wsgi-py3`.
   - Python virtual environment with `Flask` and `psycopg2-binary`.
   - Apache virtual host with `WSGIDaemonProcess` and direct static `Alias /media /app/uploads`.
   - Host port `8000` mapped to container port `80`.
   - Depends on `db` with `condition: service_healthy`.
2. **`db` Service**:
   - Official image `postgres:16`.
   - Native healthcheck: `pg_isready -U video_user -d videos`.
   - Dedicated named volume `db_data` for database state persistence.
3. **Data Persistence**:
   - Database records persist in the `db_data` volume.
   - Uploaded video files persist in the `uploads` volume.
   - Both data and uploaded media survive container restarts and rebuilds.

---

## Deliverables & Directory Structure

```text
internship_task1/
├── Dockerfile              # Multi-stage Apache + mod_wsgi + Flask image
├── docker-compose.yml      # Multi-container orchestration (web + db)
├── apache.conf             # Apache VirtualHost & WSGI daemon configuration
├── web_service.wsgi        # WSGI application entry point
├── web_service.py          # Flask service with PostgreSQL adapter
├── video_client.py         # Client functions: UploadVideo, GetVideoURL
├── capture_video.py        # Automation recorder entry point (--server, --view-seconds)
├── qscript.py              # Browser automation module with visual overlay
├── input.csv               # Input company dataset
├── requirements.txt        # Dependencies: flask, psycopg2-binary, requests, playwright
├── .env.example            # Environment variables template
├── .gitignore              # Standard git ignore rules
├── README.md               # Documentation and execution guide
├── tests/                  # Automated test suite
│   ├── test_service.py     # Unit tests for endpoints and DB logic
│   └── test_client.py      # Unit tests for client functions
└── video/                  # Sample recorded webm videos
    ├── Acme Berlin Tech.webm
    └── Bavaria Soft Solutions.webm
```

---

## Quick Start

### 1. Build and Start the Stack

Ensure Docker and Docker Compose are running, then launch the services:

```bash
docker compose up --build
```

To run in detached (background) mode:
```bash
docker compose up --build -d
```

Compose automatically:
1. Starts the `db` service and initializes PostgreSQL 16.
2. Runs the health check (`pg_isready`) until the database is ready to accept queries.
3. Builds and starts the `web` service once the database reports healthy.
4. Initializes the `videos` table schema and `/app/uploads` storage.

### 2. Verify Stack Status

```bash
docker compose ps
```

Check logs:
```bash
docker compose logs -f web
docker compose logs -f db
```

---

## Web Service Endpoints

The service listens on `http://127.0.0.1:8000`:

| Method | Path | Description |
|---|---|---|
| `POST` | `/upload` | Accepts multipart form with `file` (.webm) and `company_name`. Saves to `uploads/`, stores or updates record in PostgreSQL, and returns JSON with `company_name` and `video_url`. |
| `GET` | `/get_video_url?company_name=<name>` | Retrieves the public video URL for the specified company. Returns HTTP 200 JSON, or HTTP 404 if not found. |
| `GET` | `/media/<filename>` | Serves the uploaded video file directly (via Apache `Alias` and Flask) with `video/webm` MIME type for browser playback. |
| `GET` | `/videos` | Returns a list of all saved video records in JSON format. |
| `GET` | `/health` | Health check endpoint returning database connectivity status (`HTTP 200`). |

### Quick API Checks

```bash
# Health check
curl http://127.0.0.1:8000/health

# List video records
curl http://127.0.0.1:8000/videos

# Query video URL by company name
curl "http://127.0.0.1:8000/get_video_url?company_name=Acme%20Berlin%20Tech"
```

---

## Running the Video Recorder with Upload & Preview

While the Docker Compose stack is running, execute the recorder from your host:

```bash
# Preview each video in Chromium for 5 seconds after upload
python capture_video.py --server http://127.0.0.1:8000 --view-seconds 5

# Interactive preview (keeps browser open until Enter is pressed)
python capture_video.py --server http://127.0.0.1:8000 --view-seconds 0
```

---

## Verifying Persistence Across Container Restarts

1. Upload a video (e.g. via `capture_video.py` or curl).
2. Stop the containers:
   ```bash
   docker compose down
   ```
3. Restart the containers without wiping volumes:
   ```bash
   docker compose up -d
   ```
4. Query the stored video:
   ```bash
   curl http://127.0.0.1:8000/videos
   curl "http://127.0.0.1:8000/get_video_url?company_name=Acme%20Berlin%20Tech"
   ```
   Both the PostgreSQL database records and the uploaded video files in `/app/uploads` are preserved intact.

---

## Running Automated Tests

Run unit tests inside the `web` container:
```bash
docker compose exec web python -m unittest discover -s tests -v
```

Or run locally on host:
```bash
python -m unittest discover -s tests -v
```

---

## Acceptance Checklist

- [x] `docker compose up --build` starts both containers without errors.
- [x] `POST /upload` uploads a video and returns a working URL.
- [x] `GET /get_video_url?company_name=...` returns the URL (HTTP 200) or 404 for unknown names.
- [x] After `docker compose down` and `docker compose up`, data and videos are preserved.
- [x] `web` waits for `db` readiness (`service_healthy` condition + startup retry loop) and never crashes on startup.
- [x] Database credentials passed via environment variables without hardcoded secrets.
