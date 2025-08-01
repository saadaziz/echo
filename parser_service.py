from flask import Flask, request, jsonify
from log_utils import setup_logging
app = Flask(__name__)
logger = setup_logging("Parser")
import requests

def log_to_central(service, level, message):
    try:
        requests.post(
            "http://localhost:5020/log",
            json={"service": service, "level": level, "message": message},
            timeout=2
        )
    except Exception as e:
        logger.error(f"Failed to log to central: {e}")

@app.route("/parse", methods=["POST"])
def parse():
    file = request.files["file"]
    text = file.read().decode(errors="ignore")
    logger.info(f"Parsed {len(text)} chars from doc.")
    log_to_central("Parser", "INFO", f"Parsed {len(text)} chars from doc.")
    return jsonify({"text": text[:20000]})

if __name__ == "__main__":
    app.run(port=5010)
