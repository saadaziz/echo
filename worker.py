import time
import sqlite3
from log_utils import setup_logging
import requests
import os
from dotenv import load_dotenv
load_dotenv()
import requests
import sqlite3

DB = "jobs.db"  # Or your path

def init_embedding_db():
    with sqlite3.connect(DB) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS embeddings (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                chunk_index INTEGER,
                chunk_text TEXT,
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

if __name__ == "__main__":
    init_embedding_db()

def log_to_central(service, level, message):
    try:
        requests.post(
            "http://localhost:5020/log",
            json={"service": service, "level": level, "message": message},
            timeout=2
        )
    except Exception as e:
        logger.error(f"Failed to log to central: {e}")

UPLOAD_DIR = "doc_store"
logger = setup_logging("Worker")
PARSER_URL = "http://localhost:5010/parse"  

while True:
    with sqlite3.connect(DB) as conn:
        job = conn.execute(
            "SELECT id, filename FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
        ).fetchone()
    if job:
        job_id, filename = job
        with sqlite3.connect(DB) as conn:
            conn.execute("UPDATE jobs SET status=? WHERE id=?", ("running", job_id))
        logger.info(f"Processing job {job_id}")
        log_to_central("Parser", "INFO", f"Processing job {job_id}")
        try:
            with open(f"{UPLOAD_DIR}/{filename}", "rb") as f:
                resp = requests.post(PARSER_URL, files={"file": f})
            if resp.ok:
                parsed = resp.json()["text"]
                with sqlite3.connect(DB) as conn:
                    conn.execute("UPDATE jobs SET status=?, result=? WHERE id=?", ("complete", parsed[:10000], job_id))
                logger.info(f"Job {job_id} complete.")
            else:
                with sqlite3.connect(DB) as conn:
                    conn.execute("UPDATE jobs SET status=? WHERE id=?", ("failed", job_id))
                logger.error(f"Job {job_id} failed with code {resp.status_code}.")
        except Exception as e:
            with sqlite3.connect(DB) as conn:
                conn.execute("UPDATE jobs SET status=? WHERE id=?", ("failed", job_id))
            logger.error(f"Job {job_id} failed: {str(e)}")
            log_to_central("Parser", "ERROR", f"Job {job_id} failed: {str(e)}")
    time.sleep(5)
