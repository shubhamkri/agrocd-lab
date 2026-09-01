import os
from flask import Flask, jsonify

app = Flask(__name__)

VERSION = os.environ.get("APP_VERSION", "v1")
COLOR = os.environ.get("APP_COLOR", "blue")

@app.get("/")
def home():
    return jsonify(
        message=f"Hello from {VERSION}!",
        color=COLOR,
        hostname=os.environ.get("HOSTNAME", "unknown"),
    )

@app.get("/healthz")
def healthz():
    return jsonify(status="ok")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
