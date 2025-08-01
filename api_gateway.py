import os
import uuid
from flask import Flask, request, jsonify
from log_utils import setup_logging
import sqlite3
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
import logging
import requests
from datetime import datetime
import pytz  # pip install pytz
PACIFIC = pytz.timezone("America/Los_Angeles")
def log_to_central(service, level, message):
    try:
        requests.post(
            "http://localhost:5020/log",
            json={"service": service, "level": level, "message": message},
            timeout=2
        )
    except Exception as e:
        # Always log local in case central is down
        logger.error(f"Failed to log to central: {e}")

load_dotenv()
UPLOAD_DIR = "doc_store"
os.makedirs(UPLOAD_DIR, exist_ok=True)
logger = setup_logging("API Gateway")
DB = "jobs.db"

def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                filename TEXT,
                status TEXT,
                result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

def create_app():
    
    # # -------------------------------------------------------------
    # WARNING
    # # -------------------------------------------------------------
    # Do not deploy the following on production
    #print("Loaded OpenAI API Key:", os.environ.get("OPENAI_API_KEY"))
    
    app = Flask(__name__)

    @app.route("/documents", methods=["POST"])
    def upload_document():
        file = request.files["file"]
        job_id = str(uuid.uuid4())
        filename = f"{job_id}_{file.filename}"
        file.save(os.path.join(UPLOAD_DIR, filename))
        with sqlite3.connect(DB) as conn:
            conn.execute(
                "INSERT INTO jobs (id, filename, status) VALUES (?, ?, ?)",
                (job_id, filename, "queued"),
            )
        logger.info(f"File uploaded: {filename}, job_id: {job_id}")
        log_to_central("Parser", "INFO", f"File uploaded: {filename}, job_id: {job_id}")
        return jsonify({"job_id": job_id}), 201

    @app.route("/jobs/<job_id>", methods=["GET"])
    def get_job_status(job_id):
        with sqlite3.connect(DB) as conn:
            row = conn.execute(
                "SELECT status, result FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if not row:
                return jsonify({"error": "Job not found"}), 404
            return jsonify({"job_id": job_id, "status": row[0], "result": row[1]})

    @app.route("/query", methods=["POST"])
    def query():
        from openai import OpenAI
        data = request.json
        question = data.get("question", "")
        model = data.get("model", "openai")
        logger.info(f"Received query: {question} [model={model}]")
        log_to_central("Query", "INFO", f"Query received: {question} [model={model}]")

        with sqlite3.connect(DB) as conn:
            rows = conn.execute(
                "SELECT result FROM jobs WHERE status='complete' AND result IS NOT NULL"
            ).fetchall()
            context_chunks = [r[0] for r in rows]
        context = "\n\n".join(context_chunks)
        logger.info(f"Query context: {context[:400]}...")  # Log start of context
        log_to_central("Query", "INFO", f"Query context (truncated): {context[:400]}...")

        if not context.strip():
            msg = "No documents found. Please upload and process files before querying."
            logger.warning(msg)
            log_to_central("Query", "WARN", msg)
            return jsonify({"answer": msg})

        prompt = (
            f"You are a helpful assistant. Given the following documents, answer the question.\n"
            f"DOCUMENTS:\n{context}\n\nQUESTION: {question}\nANSWER: "
        )

        # Route to correct backend
        if model == "ollama":
            import requests
            try:
                logger.info(f"Routing query to Ollama")
                log_to_central("Query", "INFO", "Routing query to Ollama backend")
                r = requests.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "llama3",
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=30
                )
                answer = r.json().get("response", "(No response from Ollama)")
            except Exception as e:
                answer = f"Ollama error: {e}"
                logger.error(answer)
                log_to_central("Query", "ERROR", answer)
        else:
            logger.info(f"Routing query to OpenAI")
            log_to_central("Query", "INFO", "Routing query to OpenAI backend")
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0
            )
            answer = response.choices[0].message.content.strip()
        logger.info(f"Query answer: {answer}")
        log_to_central("Query", "INFO", f"Query answer: {answer}")

        return jsonify({"answer": answer})

    @app.route("/")
    def home():
        # List jobs
        with sqlite3.connect(DB) as conn:
            jobs = conn.execute("SELECT id, filename, status, result FROM jobs ORDER BY created_at DESC").fetchall()
        return render_template("home.html", jobs=jobs)

    @app.route("/upload", methods=["GET", "POST"])
    def upload_page():
        msg = ""
        if request.method == "POST":
            file = request.files["file"]
            job_id = str(uuid.uuid4())
            filename = f"{job_id}_{file.filename}"
            file.save(os.path.join(UPLOAD_DIR, filename))
            with sqlite3.connect(DB) as conn:
                conn.execute(
                    "INSERT INTO jobs (id, filename, status) VALUES (?, ?, ?)",
                    (job_id, filename, "queued"),
                )
            logger.info(f"File uploaded from UI: {filename}, job_id: {job_id}")
            log_to_central("Parser", "INFO", f"File uploaded from UI: {filename}, job_id: {job_id}")
            msg = f"Uploaded! Job ID: {job_id}"
        return render_template("upload.html", msg=msg)

    @app.route("/query-ui", methods=["GET", "POST"])
    def query_ui():
        answer = None
        question = ""
        model = "openai"  # Default
        if request.method == "POST":
            question = request.form.get("question", "")
            model = request.form.get("model", "openai")
            # Grab context from jobs
            with sqlite3.connect(DB) as conn:
                rows = conn.execute(
                    "SELECT result FROM jobs WHERE status='complete' AND result IS NOT NULL"
                ).fetchall()
                context = "\n\n".join(r[0] for r in rows)
            if not context.strip():
                answer = "No documents found. Please upload and process files before querying."
            else:
                if model == "ollama":
                    # Route to Ollama local instance
                    import requests
                    # You can run ollama REST locally: https://github.com/jmorganca/ollama/blob/main/docs/api.md
                    prompt = f"You are a helpful assistant. Given the following documents, answer the question.\nDOCUMENTS:\n{context}\n\nQUESTION: {question}\nANSWER: "
                    try:
                        r = requests.post(
                            "http://localhost:11434/api/generate",
                            json={
                                "model": "llama3",  # Or whichever you pulled
                                "prompt": prompt,
                                "stream": False
                            },
                            timeout=30
                        )
                        answer = r.json().get("response", "(No response from Ollama)")
                    except Exception as e:
                        answer = f"Ollama error: {e}"
                else:
                    # Default: OpenAI (cloud)
                    from openai import OpenAI
                    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                    prompt = f"You are a helpful assistant. Given the following documents, answer the question.\nDOCUMENTS:\n{context}\n\nQUESTION: {question}\nANSWER: "
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=256,
                        temperature=0
                    )
                    answer = response.choices[0].message.content.strip()
        return render_template("query.html", answer=answer, question=question, model=model)





    @app.route("/logs")
    def logs():
        with sqlite3.connect("logs.db") as conn:
            logs = conn.execute("SELECT service, level, message, created_at FROM logs ORDER BY created_at DESC LIMIT 100").fetchall()
        # Convert to dicts for frontend
        result = []
        for l in logs:
            # Assume created_at is a string like '2025-08-01 01:23:45'
            utc_dt = datetime.strptime(l[3], "%Y-%m-%d %H:%M:%S")
            pacific_dt = utc_dt.replace(tzinfo=pytz.UTC).astimezone(PACIFIC)
            formatted_time = pacific_dt.strftime("%Y-%m-%d %I:%M:%S %p %Z")
            result.append({
                "service": l[0],
                "level": l[1],
                "message": l[2],
                "created_at": formatted_time
            })
        return jsonify(result)




    return app




if __name__ == "__main__":
    init_db()
    app = create_app()
    app.run(port=5000, debug=True)
