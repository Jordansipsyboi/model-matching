import os
import threading
import time
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

import database

app = Flask(__name__)
app.secret_key = "mm-secret-2025-xk9"

ADMIN_PASSWORD = "eden2009"

database.init_db()
database.seed_db()


# ── Public routes ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/find-models")
def find_models():
    return render_template("find-models.html")


@app.route("/list-models")
def list_models():
    return render_template("list-models.html")


@app.route("/api/models")
def api_models():
    return jsonify(database.get_all_models())


@app.route("/api/submit-agency", methods=["POST"])
def submit_agency():
    agency_name    = request.form.get("agencyName", "").strip()
    agency_website = request.form.get("agencyWebsite", "").strip()
    contact_name   = request.form.get("contactName", "").strip()
    contact_email  = request.form.get("contactEmail", "").strip()
    market         = request.form.get("agencyMarket", "").strip()
    notes          = request.form.get("notes", "").strip()

    if not all([agency_name, agency_website, contact_name, contact_email, market]):
        return jsonify({"error": "Missing required fields"}), 400

    database.save_agency(agency_name, agency_website, contact_name, contact_email, market, notes)
    return jsonify({"status": "ok", "message": "Agency registered"})


# ── Admin routes ───────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "Wrong password."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    agencies = database.get_all_agencies()
    models   = database.get_all_models()
    return render_template("admin.html", agencies=agencies, models=models)


@app.route("/admin/crawl/<int:agency_id>", methods=["POST"])
def admin_crawl(agency_id):
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 401

    import asyncio
    from crawler import crawl_agency

    conn = database.get_connection()
    row = conn.execute("SELECT * FROM agencies WHERE id = ?", (agency_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Agency not found"}), 404

    agency = dict(row)

    def do_crawl():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(crawl_agency(agency))
        loop.close()

    t = threading.Thread(target=do_crawl, daemon=True)
    t.start()
    return jsonify({"status": "ok", "message": f"Crawling {agency['agency_name']}..."})



@app.route("/admin/agency-status/<int:agency_id>")
def admin_agency_status(agency_id):
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 401
    conn = database.get_connection()
    row = conn.execute("SELECT last_crawled_at FROM agencies WHERE id = ?", (agency_id,)).fetchone()
    conn.close()
    return jsonify({"last_crawled_at": row["last_crawled_at"] if row else None})


# ── Nightly scheduler ──────────────────────────────────────────

def run_nightly_crawl():
    """Runs in a background thread, crawls all agencies every 24h."""
    while True:
        time.sleep(24 * 60 * 60)
        try:
            import asyncio
            from crawler import get_agencies_to_crawl, crawl_agency
            agencies = get_agencies_to_crawl()
            if agencies:
                print(f"[Scheduler] Crawling {len(agencies)} agencies...")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                for agency in agencies:
                    loop.run_until_complete(crawl_agency(agency))
                loop.close()
                print("[Scheduler] Done.")
        except Exception as e:
            print(f"[Scheduler] Error: {e}")


scheduler_thread = threading.Thread(target=run_nightly_crawl, daemon=True)
scheduler_thread.start()


if __name__ == "__main__":
    app.run(debug=True)
