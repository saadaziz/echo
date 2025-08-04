import os
import uuid
import sqlite3
import logging
import requests
import pytz
import jwt
import time, hashlib
import uuid
from urllib.parse import urlencode
from datetime import datetime, timezone
from openai import OpenAI
from flask import Flask, request, redirect, session, url_for, jsonify, make_response, render_template
from log_utils import setup_logging
from dotenv import load_dotenv
import json


# ── Load configuration ────────────────────────────────────────────────────────
load_dotenv()

# todo: move these into config
OIDC_CLIENT_ID        = os.getenv("OIDC_CLIENT_ID", "browser-ui")
OIDC_CLIENT_SECRET    = os.getenv("OIDC_CLIENT_SECRET", "dev-client-secret")
OIDC_AUTH_URL         = os.getenv("OIDC_AUTH_URL", "https://aurorahours.com/identity-backend/authorize")
OIDC_TOKEN_URL        = os.getenv("OIDC_TOKEN_URL", "https://aurorahours.com/identity-backend/token")
OIDC_ISSUER           = os.getenv("JWT_ISSUER", "https://aurorahours.com/identity-backend")
OIDC_REDIRECT_URI     = os.getenv("OIDC_REDIRECT_URI", "http://localhost:5000/callback")
SESSION_SECRET        = os.getenv("FLASK_SECRET_KEY", "dev-session")
JWT_EXPIRATION_SECS   = int(os.getenv("JWT_EXPIRATION_MINUTES", "15")) * 60

PACIFIC               = pytz.timezone("America/Los_Angeles")
UPLOAD_DIR            = "doc_store"
DB_PATH               = "jobs.db"

os.makedirs(UPLOAD_DIR, exist_ok=True)

logger = setup_logging("API Gateway") or logging.getLogger("api_gateway")
logger.setLevel(logging.INFO)

def log_to_central(service: str, level: str, message: str):
    try:
        requests.post("http://localhost:5020/log",
                      json={"service": service, "level": level, "message": message},
                      timeout=2)
    except Exception as e:
        logger.error(f"Failed to log to central: {e}")



def create_app():
    app = Flask(__name__)
    app.secret_key = SESSION_SECRET

    # --- tojson Jinja Filter in Your Flask App ---
    def tojson_filter(value, indent=2):
        # If already a string, try to parse to dict/list
        try:
            parsed = json.loads(value)
            return json.dumps(parsed, indent=indent, ensure_ascii=False)
        except Exception:
            return value  # fallback to original

    app.jinja_env.filters['tojson'] = tojson_filter

    # --- Jinja2 log date formatter filter ---
    def datetime_fmt(dt_str):
        try:
            dt = datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%b %d, %I:%M %p")
        except Exception:
            return dt_str
        
    app.jinja_env.filters['datetime_fmt'] = datetime_fmt

    def is_logged_in() -> bool:
        return "id_token" in session

    def get_id_token() -> str:
        return session.get("id_token")

    def verify_id_token(token: str) -> dict:
        start = time.time()
        try:
            # For traceability, hash the token (never log the full thing!)
            token_hash = hashlib.sha256(token.encode()).hexdigest()[:12]

            claims = jwt.decode(token, options={"verify_signature": False})
            logger.info(f"[verify_id_token] TokenHash={token_hash} Decoded claims: {claims}")
            log_to_central("Identity", "DEBUG", f"[verify_id_token] TokenHash={token_hash} Claims: {claims}")

            # Trace the subject (user) as soon as we can
            sub = claims.get("sub", "(none)")
            aud = claims.get("aud")
            iss = claims.get("iss")
            exp = claims.get("exp")
            iat = claims.get("iat")

            # Audience check
            if aud != OIDC_CLIENT_ID:
                msg = f"Audience mismatch: got {aud}, expected {OIDC_CLIENT_ID} (sub={sub}, TokenHash={token_hash})"
                logger.error(msg)
                log_to_central("Identity", "ERROR", msg)
                raise ValueError("Invalid audience")

            # Issuer check
            if iss != OIDC_ISSUER:
                msg = f"Issuer mismatch: got {iss}, expected {OIDC_ISSUER} (sub={sub}, TokenHash={token_hash})"
                logger.error(msg)
                log_to_central("Identity", "ERROR", msg)
                raise ValueError("Invalid issuer")

            # Expiry check
            now = int(time.time())
            if exp and exp < now:
                exp_str = datetime.utcfromtimestamp(exp).isoformat() + "Z"
                iat_str = datetime.utcfromtimestamp(iat).isoformat() + "Z" if iat else "(unknown)"
                msg = f"Token expired at {exp_str}, issued at {iat_str}, now={datetime.utcfromtimestamp(now).isoformat()}Z (sub={sub}, TokenHash={token_hash})"
                logger.error(msg)
                log_to_central("Identity", "ERROR", msg)
                raise ValueError("ID token expired")

            elapsed = round(time.time() - start, 4)
            msg = f"[verify_id_token] Token valid for sub={sub} (TokenHash={token_hash}), checked in {elapsed}s"
            logger.info(msg)
            log_to_central("Identity", "INFO", msg)
            return claims

        except Exception as e:
            logger.error(f"[verify_id_token] JWT verification failed: {e}")
            log_to_central("Identity", "ERROR", f"[verify_id_token] JWT verification failed: {e}")
            raise ValueError(f"Invalid token: {str(e)}")

    def require_login():
        if not is_logged_in():
            return redirect(url_for("login"))
        try:
            user = verify_id_token(get_id_token())
            return user
        except ValueError as e:
            session.clear()
            logger.warning(f"ID token validation failed: {e}")
            return redirect(url_for("login"))

    @app.route("/login")
    def login():
        # Generate a new state for this login request
        state = str(uuid.uuid4())
        session["oidc_state"] = state

        # Prepare OIDC parameters
        params = {
            "client_id":     OIDC_CLIENT_ID,
            "redirect_uri":  OIDC_REDIRECT_URI,
            "response_type": "code",
            "scope":         "openid",
            "state":         state
        }
        url = OIDC_AUTH_URL + "?" + urlencode(params)
        
        # Gather request context for observability
        ip = request.remote_addr
        ua = request.headers.get("User-Agent", "(none)")
        sess_id = session.get('_id', 'no-session-id')  # Flask does not use '_id' by default, just example

        log_msg = (f"[login] Redirecting to OIDC auth: state={state}, ip={ip}, ua={ua}, "
                f"session_id={sess_id}, params={params}")

        logger.info(log_msg)
        log_to_central("Identity", "INFO", log_msg)

        return redirect(url)

    @app.route("/callback")
    def callback():
        start = time.time()
        trace_id = str(uuid.uuid4())  # Use per-request trace for log correlation
        ip = request.remote_addr
        ua = request.headers.get("User-Agent", "")
        session_id = session.get("session_id", "-")

        # Step 1: Error from OIDC
        if "error" in request.args:
            err = request.args.get("error")
            msg = f"[callback] OIDC error: {err} | ip={ip}, ua={ua}, session_id={session_id}, trace_id={trace_id}"
            logger.error(msg)
            log_to_central("Auth-Client", "ERROR", msg)
            return f"OIDC returned error: {err}", 400

        code = request.args.get("code")
        state = request.args.get("state")
        code_hash = hashlib.sha256((code or "no-code").encode()).hexdigest()[:12] if code else "-"
        expected_state = session.get("oidc_state")
        if not code or not state or state != expected_state:
            msg = (f"[callback] Missing/invalid state or code | code_hash={code_hash}, state={state}, expected_state={expected_state}, "
                f"ip={ip}, ua={ua}, session_id={session_id}, trace_id={trace_id}")
            logger.error(msg)
            log_to_central("Auth-Client", "ERROR", msg)
            return "Missing or invalid state or code", 400

        token_req = {
            "grant_type":   "authorization_code",
            "code":         code,
            "client_id":    OIDC_CLIENT_ID,
            "client_secret":OIDC_CLIENT_SECRET,
            "redirect_uri": OIDC_REDIRECT_URI
        }
        try:
            r = requests.post(OIDC_TOKEN_URL, data=token_req, timeout=10)
            r.raise_for_status()
        except Exception as e:
            body = getattr(r, 'text', None)
            msg = (f"[callback] Token request failed: {e} | body={body}, code_hash={code_hash}, ip={ip}, ua={ua}, "
                f"session_id={session_id}, trace_id={trace_id}")
            logger.error(msg)
            log_to_central("Auth-Client", "ERROR", msg)
            return f"Token exchange error: {e}", 502

        td = r.json()
        id_token = td.get("id_token")
        if not id_token:
            msg = (f"[callback] No id_token in token response: {td}, code_hash={code_hash}, "
                f"ip={ip}, ua={ua}, session_id={session_id}, trace_id={trace_id}")
            logger.error(msg)
            log_to_central("Auth-Client", "ERROR", msg)
            return "Token endpoint did not return id_token", 502

        try:
            claims = verify_id_token(id_token)
        except ValueError as e:
            msg = (f"[callback] ID token invalid: {e}, code_hash={code_hash}, ip={ip}, ua={ua}, "
                f"session_id={session_id}, trace_id={trace_id}")
            logger.error(msg)
            log_to_central("Auth-Client", "ERROR", msg)
            return f"ID token invalid: {str(e)}", 401

        session["id_token"] = id_token
        session.pop("oidc_state", None)
        user = {
            "sub":      claims.get("sub"),
            "iss":      claims.get("iss"),
            "aud":      claims.get("aud"),
            "scope":    claims.get("scope"),
            "issued_at": claims.get("iat"),
            "expires_at": claims.get("exp")
        }
        if "email" in claims: user["email"] = claims.get("email")
        if "picture" in claims: user["picture"] = claims.get("picture")

        elapsed = round(time.time() - start, 4)
        msg = (f"[callback] Login success: sub={user.get('sub')}, email={user.get('email', '-')}, aud={user['aud']}, "
            f"code_hash={code_hash}, ip={ip}, ua={ua}, session_id={session_id}, trace_id={trace_id}, "
            f"timing={elapsed}s")
        logger.info(msg)
        log_to_central("Auth-Client", "INFO", msg)

        return redirect(url_for("home"))


    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    def home():
        user = require_login()
        if not isinstance(user, dict): return user
        with sqlite3.connect(DB_PATH) as conn:
            jobs = conn.execute(
                "SELECT id, filename, status, result FROM jobs ORDER BY created_at DESC"
            ).fetchall()
        return render_template("home.html", user=user, jobs=jobs)

    @app.route("/upload", methods=["GET", "POST"])
    def upload_page():
        user = require_login()
        if not isinstance(user, dict): return user
        msg = ""
        if request.method == "POST":
            file = request.files.get("file")
            if file:
                job_id = str(uuid.uuid4())
                filename = f"{job_id}_{file.filename}"
                store_fn = os.path.join(UPLOAD_DIR, filename)
                file.save(store_fn)
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute(
                        "INSERT INTO jobs (id, filename, status) VALUES (?, ?, ?)",
                        (job_id, filename, "queued")
                    )
                logger.info(f"Uploaded: {filename}")
                log_to_central("Parser", "INFO", f"Uploaded file: {filename}")
                msg = f"Job queued: {job_id}"
        return render_template("upload.html", user=user, msg=msg)

    @app.route("/query-ui", methods=["GET", "POST"])
    def query_ui():
        user = require_login()
        if not isinstance(user, dict):
            return user

        start_time = time.time()
        logger.info(f"Query-UI: Method={request.method}, User={user.get('sub')}, IP={request.remote_addr}")
        log_to_central("Query-UI", "INFO", f"Query-UI: Method={request.method}, User={user.get('sub')}, IP={request.remote_addr}")

        answer = None
        question = ""
        model = "openai"  # Default

        if request.method == "POST":
            question = request.form.get("question", "").strip()
            model = request.form.get("model", "openai").lower()
            logger.info(f"Query from UI: '{question}' [model={model}]")
            log_to_central("Query-UI", "INFO", f"Received question: {question}")

            with sqlite3.connect(DB_PATH) as conn:
                rows = conn.execute(
                    "SELECT result FROM jobs WHERE status='complete' AND result IS NOT NULL"
                ).fetchall()
                logger.info(f"Query-UI: {len(rows)} complete docs found for context.")
                log_to_central("Query-UI", "INFO", f"Query-UI: {len(rows)} complete docs found for context.")
                context = "\n\n".join(r[0] for r in rows)
                log_to_central("Query-UI", "INFO", f"Query-UI: Context: {context}")

            if not context.strip():
                answer = "No documents found. Please upload and process files before querying."
                log_to_central("Query-UI", "INFO", "No documents found. Please upload and process files before querying.")
            else:
                if model == "ollama":
                    # Route to Ollama local instance
                    import requests
                    prompt = (
                        "You are a helpful assistant. Given the following documents, answer the question."
                        f"\nDOCUMENTS:\n{context}\n\nQUESTION: {question}\nANSWER: "
                    )
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
                    try:
                        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                        prompt = (
                            "You are a helpful assistant. Given the following documents, answer the question."
                            f"\nDOCUMENTS:\n{context}\n\nQUESTION: {question}\nANSWER: "
                        )
                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=256,
                            temperature=0
                        )
                        answer = response.choices[0].message.content.strip()
                    except Exception as e:
                        answer = f"OpenAI error: {e}"

        # Make sure you pass `model=model` so the dropdown stays selected!
        return render_template("query.html", user=user, answer=answer, question=question, model=model)


    @app.route("/logs")
    def logs():
        # Logs endpoint is PUBLIC for now!
        import warnings
        warnings.warn("LOGS endpoint is currently public! Remove this before production.")

        with sqlite3.connect("logs.db") as conn:
            raw = conn.execute(
                "SELECT service, level, message, created_at "
                "FROM logs ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        entries = []
        for s, lev, msg, ts in raw:
            pac = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")\
                     .replace(tzinfo=pytz.UTC).astimezone(PACIFIC)
            entries.append({
                "service": s,
                "level": lev,
                "message": msg,
                "created_at": pac.strftime("%Y-%m-%d %H:%M:%S %p %Z")
            })
        # Render logs.html (see template below)
        return render_template("logs.html", logs=entries, logs_public=True)
    
    @app.route("/logs.json")
    def logs_json():
        import pytz
        from datetime import datetime
        PACIFIC = pytz.timezone("America/Los_Angeles")
        with sqlite3.connect("logs.db") as conn:
            rows = conn.execute(
                "SELECT service, level, message, created_at FROM logs ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        result = []
        for s, level, msg, ts in rows:
            pac = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.UTC).astimezone(PACIFIC)
            result.append({
                "service": s,
                "level": level,
                "message": msg,
                "created_at": pac.strftime("%Y-%m-%d %I:%M:%S %p %Z")
            })
        return jsonify(result)



    @app.route("/ping")
    def ping():
        req_id = str(uuid.uuid4())
        ts = time.time()
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        ua = request.headers.get("User-Agent", "-")
        headers = dict(request.headers)
        params = dict(request.args)
        session_id = session.get("id_token", "no-session-id")  # Adjust as needed

        log_entry = {
            "event": "ping",
            "req_id": req_id,
            "ip": ip,
            "user_agent": ua,
            "params": params,
            "headers": {k: v for k, v in headers.items() if k.lower() not in ["cookie", "authorization"]},
            "session_id": session_id,
            "timestamp": ts
        }

        # Local and central logging
        logger.info(f"[ping] {log_entry}")
        log_to_central("API Gateway", "INFO", f"[ping] {log_entry}")

        # TODO: Implement rate limiting/DDoS block logic here.

        return "OK", 200


    return app

def get_required_env(key):
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
    val = os.getenv(key)
    if dev_mode:
        return val  # In dev, accept whatever's set (even if None or a placeholder)
    if not val or val.startswith("<") or "secret" in val:
        raise Exception(f"{key} not set or still uses a placeholder!")
    return val


# Only in production:
JWT_SECRET_KEY = get_required_env("JWT_SECRET_KEY")
FLASK_SECRET_KEY = get_required_env("FLASK_SECRET_KEY")
OPENAI_API_KEY = get_required_env("OPENAI_API_KEY")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                filename TEXT,
                status TEXT,
                result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

if __name__ == "__main__":
    init_db()
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=True)
