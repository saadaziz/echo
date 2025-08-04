import time
import sqlite3
from log_utils import setup_logging
import requests
import os
from dotenv import load_dotenv
import traceback

load_dotenv()

DB = "jobs.db"  

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
    logger.debug("Checking for queued jobs...")
    with sqlite3.connect(DB) as conn:
        job = conn.execute(
            "SELECT id, filename FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
        ).fetchone()

    if job:
        job_id, filename = job
        with sqlite3.connect(DB) as conn:
            conn.execute("UPDATE jobs SET status=? WHERE id=?", ("running", job_id))
        logger.info(f"Processing job {job_id} - file: {filename}")
        log_to_central("Parser", "INFO", f"Processing job {job_id}")

        try:
            with open(f"{UPLOAD_DIR}/{filename}", "rb") as f:
                resp = requests.post(PARSER_URL, files={"file": f})

            if resp.ok:
                parsed = resp.json().get("text", "")
                size = len(parsed)
                snippet = parsed[:500].replace("\n", " ")  

                with sqlite3.connect(DB) as conn:
                    conn.execute("UPDATE jobs SET status=?, result=? WHERE id=?", ("complete", parsed[:10000], job_id))

                logger.info(f"Job {job_id} complete. Parsed text size: {size} chars. Snippet: {snippet}")
                log_to_central("Parser", "INFO", f"Job {job_id} complete. Parsed text size: {size}. Snippet: {snippet}")

            else:
                with sqlite3.connect(DB) as conn:
                    conn.execute("UPDATE jobs SET status=? WHERE id=?", ("failed", job_id))
                logger.error(f"Job {job_id} failed with HTTP status {resp.status_code}. Response: {resp.text}")
                log_to_central("Parser", "ERROR", f"Job {job_id} failed. HTTP {resp.status_code}: {resp.text}")

        except Exception as e:
            with sqlite3.connect(DB) as conn:
                conn.execute("UPDATE jobs SET status=? WHERE id=?", ("failed", job_id))
            tb_str = traceback.format_exc()
            logger.error(f"Job {job_id} failed with exception: {str(e)}", exc_info=True)
            log_to_central("Parser", "ERROR", f"Job {job_id} failed with exception: {str(e)}\nTraceback:\n{tb_str}")

    else:
        logger.debug("No queued jobs found, worker sleeping...")

    time.sleep(5)
