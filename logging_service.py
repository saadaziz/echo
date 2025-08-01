from flask import Flask, request, jsonify
from log_utils import setup_logging
import sqlite3
app = Flask(__name__)
logger = setup_logging("Logging Service")
DB = "logs.db"

def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY,
                service TEXT,
                level TEXT,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

@app.route("/log", methods=["POST"])
def log():
    data = request.json
    with sqlite3.connect(DB) as conn:
        conn.execute(
            "INSERT INTO logs (service, level, message) VALUES (?, ?, ?)",
            (data["service"], data["level"], data["message"]),
        )
    logger.info(f"LOG: {data}")
    return jsonify({"ok": True})

if __name__ == "__main__":
    init_db()
    app.run(port=5020)
