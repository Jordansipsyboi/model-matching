import os
import threading
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

import database

app = Flask(__name__)
app.secret_key = "mm-secret-2025-xk9"

ADMIN_PASSWORD = "eden2009"

database.init_db()


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
    return jsonify(database.get_all_models(active_only=True))


@app.route("/api/search-models", methods=["POST"])
def search_models():
    def _ints(key, default=None):
        v = request.form.get(key)
        return int(v) if v and v.strip() else default

    def _list(key):
        v = request.form.get(key, "")
        return [x.strip() for x in v.split(",") if x.strip()] if v else []

    filters = {
        "gender":       _list("gender"),
        "height_min":   _ints("height_min"),
        "height_max":   _ints("height_max"),
        "waist_min":    _ints("waist_min"),
        "waist_max":    _ints("waist_max"),
        "chest_min":    _ints("chest_min"),
        "chest_max":    _ints("chest_max"),
        "hips_min":     _ints("hips_min"),
        "hips_max":     _ints("hips_max"),
        "nationalities": _list("nationalities"),
        "hair_lengths":  _list("hair_lengths"),
        "hair_colors":   _list("hair_colors"),
        "eye_colors":    _list("eye_colors"),
        "age_min":       _ints("age_min"),
        "age_max":       _ints("age_max"),
    }

    # Step 1: filter by non-photo criteria
    candidates = database.get_models_for_search(filters)

    # Step 2: keyword filter (work types, looks, agency, name)
    keyword = request.form.get("keyword", "").strip().lower()
    work_types = _list("work_types")
    looks = _list("looks")
    if keyword or work_types or looks:
        def matches(m):
            if keyword:
                searchable = f"{m['english']} {m['korean']} {m['gender']} {m['nationality']} {m['hair_color']} {m['hair_length']} {m['eye_color']} {m['agency_name']} {' '.join(m['workTypes'])} {' '.join(m['looks'])}".lower()
                if keyword not in searchable:
                    return False
            if work_types and not any(t in m["workTypes"] for t in work_types):
                return False
            if looks and not any(l in m["looks"] for l in looks):
                return False
            return True
        candidates = [m for m in candidates if matches(m)]

    # Step 3: face similarity search if photo uploaded
    photo_file = request.files.get("photo")
    threshold = float(request.form.get("threshold", "0.10"))

    if photo_file:
        try:
            import numpy as np
            import tempfile
            import os as _os
            from face1n import AuraFaceComparator

            comparator = AuraFaceComparator()

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                photo_file.save(tmp.name)
                tmp_path = tmp.name

            try:
                query_emb, query_info = comparator.extract_face_embedding_optimized(tmp_path)
            finally:
                _os.unlink(tmp_path)

            if query_emb is not None:
                query_emb = query_emb.astype("float32")
                norm = np.linalg.norm(query_emb)
                if norm > 0:
                    query_emb = query_emb / norm

                scored = []
                no_embedding = []
                for m in candidates:
                    emb_bytes = m.pop("_face_embedding", None)
                    if emb_bytes:
                        db_emb = np.frombuffer(emb_bytes, dtype=np.float32).copy()
                        similarity = float(np.dot(query_emb, db_emb))
                        if similarity >= threshold:
                            m["similarity"] = round(similarity * 100, 1)
                            scored.append(m)
                    else:
                        m["similarity"] = None
                        no_embedding.append(m)

                scored.sort(key=lambda x: x["similarity"], reverse=True)
                candidates = scored + no_embedding
            else:
                for m in candidates:
                    m.pop("_face_embedding", None)
                    m["similarity"] = None
        except Exception as e:
            for m in candidates:
                m.pop("_face_embedding", None)
                m["similarity"] = None
            print(f"[FaceSearch] Error: {e}")
    else:
        for m in candidates:
            m.pop("_face_embedding", None)
            m["similarity"] = None

    return jsonify({"models": candidates, "total": len(candidates)})


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
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM agencies WHERE id = %s", (agency_id,))
        row = cur.fetchone()
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
    with conn.cursor() as cur:
        cur.execute("SELECT last_crawled_at FROM agencies WHERE id = %s", (agency_id,))
        row = cur.fetchone()
    conn.close()
    val = row["last_crawled_at"] if row else None
    if val and hasattr(val, "isoformat"):
        val = val.isoformat()
    return jsonify({"last_crawled_at": val})


if __name__ == "__main__":
    app.run(debug=True)
