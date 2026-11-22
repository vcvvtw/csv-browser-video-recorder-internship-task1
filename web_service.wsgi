import sys
import os

# Add application directory to path
sys.path.insert(0, "/app")

from web_service import app as application, wait_for_db

# Initialize database schema on daemon startup
try:
    wait_for_db(max_retries=20, retry_interval=1.5)
except Exception as err:
    sys.stderr.write(f"WSGI startup database check warning: {err}\n")
