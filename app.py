import os
import csv
import io
import time
import uuid
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, send_file
from checker import parse_card, run_check

app = Flask(__name__)

# Almacén en memoria de trabajos
JOBS = {}
LIVES_FILE = "Lives.txt"
LOCK = threading.Lock()


def _append_live(cc_display, msg):
    try:
        with LOCK, open(LIVES_FILE, "a", encoding="utf-8") as f:
            f.write(f"{cc_display} » {msg} » {datetime.utcnow().isoformat()}Z\n")
    except Exception:
        pass


def _worker(job_id, cards):
    job = JOBS[job_id]
    for idx, cc in enumerate(cards):
        if job["cancelled"]:
            job["status"] = "cancelled"
            return
        started = time.time()
        try:
            status, msg = run_check(cc)
        except Exception as e:
            status, msg = "Declined", f"error: {e}"
        elapsed = round(time.time() - started, 1)

        with LOCK:
            job["results"].append({
                "id": idx + 1,
                "card": cc["display"],
                "status": status,
                "message": msg,
                "time": elapsed,
            })
            job["done"] += 1

        if status == "Approved":
            _append_live(cc["display"], msg)

    job["status"] = "finished"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def api_start():
    payload = request.get_json(silent=True) or {}
    raw_text = payload.get("cards", "")

    lines = [ln.strip() for ln in raw_text.replace(",", "\n").splitlines() if ln.strip()]
    cards = []
    invalid = []
    for ln in lines:
        cc = parse_card(ln)
        if cc:
            cards.append(cc)
        else:
            invalid.append(ln)

    if not cards:
        return jsonify({"error": "No se encontraron tarjetas válidas.", "invalid": invalid}), 400

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id,
        "created": datetime.utcnow().isoformat() + "Z",
        "total": len(cards),
        "done": 0,
        "results": [],
        "status": "running",
        "cancelled": False,
        "invalid": invalid,
    }
    t = threading.Thread(target=_worker, args=(job_id, cards), daemon=True)
    t.start()

    return jsonify({"job_id": job_id, "total": len(cards), "invalid": invalid})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job no encontrado"}), 404
    with LOCK:
        return jsonify({
            "id": job["id"],
            "total": job["total"],
            "done": job["done"],
            "status": job["status"],
            "results": list(job["results"]),
            "invalid": job["invalid"],
        })


@app.route("/api/cancel/<job_id>", methods=["POST"])
def api_cancel(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job no encontrado"}), 404
    job["cancelled"] = True
    return jsonify({"ok": True})


@app.route("/api/export/<job_id>.csv")
def api_export(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job no encontrado"}), 404

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["#", "Card", "Status", "Message", "Time (s)"])
    for r in job["results"]:
        writer.writerow([r["id"], r["card"], r["status"], r["message"], r["time"]])

    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=results_{job_id}.csv"},
    )


@app.route("/api/lives")
def api_lives():
    if not os.path.isfile(LIVES_FILE):
        return Response("", mimetype="text/plain")
    return send_file(LIVES_FILE, mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)