import os
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

import database

app = Flask(__name__)
app.secret_key = "mm-secret-2025-xk9"

ADMIN_PASSWORD = "eden2009"

database.init_db()


# Load the face-recognition model once and reuse it, instead of reloading the
# whole InsightFace model on every search request (slow + noisy logs).
_face_comparator = None

def get_face_comparator():
    global _face_comparator
    if _face_comparator is None:
        from face1n import AuraFaceComparator
        _face_comparator = AuraFaceComparator()
    return _face_comparator


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
    # UI sends a display-percentage threshold (30/50/70 for Low/Medium/High).
    # Convert to transformed-space: threshold_t = REMAP_LO + (pct/100) * (REMAP_HI - REMAP_LO)
    # This guarantees that only results displaying at >= pct% are admitted.
    _REMAP_LO, _REMAP_HI = 0.10, 0.35
    _threshold_pct = float(request.form.get("threshold", "50"))
    threshold = _REMAP_LO + (_threshold_pct / 100.0) * (_REMAP_HI - _REMAP_LO)

    if photo_file:
        try:
            import numpy as np
            import tempfile
            import os as _os
            from face1n import DEFAULT_SIMILARITY_ALPHA

            comparator = get_face_comparator()

            # Load alpha from config (falls back to face1n default of 0.75)
            _cfg = database.load_config()
            alpha = float(_cfg.get("similarity_alpha", DEFAULT_SIMILARITY_ALPHA))

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

                # Detect gender of the uploaded photo and filter to same gender.
                # InsightFace genderage returns 'M' or 'F'; DB stores 'male'/'female'.
                query_gender = None
                if query_info and query_info.get("gender"):
                    raw_g = query_info["gender"]  # 'M' or 'F'
                    query_gender = "male" if raw_g == "M" else "female"

                scored = []
                for m in candidates:
                    emb_bytes = m.pop("_face_embedding", None)
                    if emb_bytes:
                        # Gender filter: skip models whose gender doesn't match query
                        if query_gender and m.get("gender") and m["gender"].lower() != query_gender:
                            m["similarity"] = None
                            continue
                        db_emb = np.frombuffer(emb_bytes, dtype=np.float32).copy()
                        raw_similarity = float(np.dot(query_emb, db_emb))
                        # Exponentiation (alpha boost) commented out — use raw cosine directly.
                        # transformed = max(0.0, raw_similarity) ** alpha
                        transformed = max(0.0, raw_similarity)
                        # transformed is used for filtering, sorting, AND display.
                        # threshold was derived from display-pct, so any model that
                        # passes is guaranteed to display at >= the selected preset %.
                        if transformed >= threshold:
                            display_pct = min(100.0, max(0.0,
                                (transformed - _REMAP_LO) / (_REMAP_HI - _REMAP_LO) * 100))
                            m["similarity"] = round(display_pct, 1)
                            scored.append(m)
                        else:
                            m["similarity"] = None
                    else:
                        m["similarity"] = None

                scored.sort(key=lambda x: x["similarity"], reverse=True)
                candidates = scored
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


# Columns for the downloadable roster template (order matters).
# Measurement columns are unit-agnostic: agencies can type cm, inches, feet'in",
# "99/39" dual format, "285MM", EU shoe sizes, etc. and the importer figures out
# the real value (see _normalize_measurement). We also accept the older
# *_cm / *_inch / *_mm column names as aliases so old templates still work.
CSV_TEMPLATE_COLUMNS = [
    "name", "korean_name", "birth_year", "gender", "nationality",
    "height", "chest", "waist", "hips", "shoes",
    "hair", "eyes", "rate_usd",
]

# Plausible cm ranges per body measurement, used to auto-detect whether an
# unlabelled number was typed in cm or inches.
_MEASURE_CM_BOUNDS = {
    "height": (120, 220),
    "chest": (60, 130),
    "waist": (45, 120),
    "hips": (60, 140),
}

PHOTO_DIR = os.path.join(os.path.dirname(__file__), "static", "model_photos")


def _slug(name):
    import re
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def _to_int(val, default=0):
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default


def _normalize_measurement(raw, kind):
    """Turn a messily-typed body measurement into a clean cm integer.

    Handles, in order of priority:
      - dual cm/imperial format "185/6'1\"", "99/39\"" -> first number is cm
      - explicit unit suffixes: "182cm", "72 cm", "28in", "28\"", "28 inch"
      - feet'inches": "6'1\"", "5'11"
      - bare numbers: auto-detected as cm or inches via plausible cm range
    Returns 0 when nothing usable is found. `kind` is one of
    height/chest/waist/hips.
    """
    import re

    if raw is None:
        return 0
    s = str(raw).strip().lower()
    if not s:
        return 0

    lo, hi = _MEASURE_CM_BOUNDS.get(kind, (0, 10**6))

    # Dual cm/imperial "<cm>/<imperial>" -> the part before the slash is cm.
    if "/" in s:
        s = s.split("/", 1)[0].strip()

    # feet'inches"  e.g. 6'1"  or  5'11
    m = re.match(r"^(\d+)\s*'\s*(\d+(?:\.\d+)?)?", s)
    if "'" in s and m:
        feet = float(m.group(1))
        inches = float(m.group(2)) if m.group(2) else 0.0
        return round((feet * 12 + inches) * 2.54)

    # Explicit unit suffix wins over guessing.
    has_cm = "cm" in s
    has_in = ("inch" in s) or ("in" in s) or ('"' in s)

    num = re.search(r"-?\d+(?:\.\d+)?", s)
    if not num:
        return 0
    val = float(num.group())

    if has_cm:
        return round(val)
    if has_in:
        return round(val * 2.54)

    # No unit given: decide by which range the bare number falls into.
    if lo <= val <= hi:
        return round(val)                 # already plausible as cm
    inch_as_cm = val * 2.54
    if lo <= inch_as_cm <= hi:
        return round(inch_as_cm)          # only makes sense as inches
    # Out of every plausible band: trust cm if it's at least in the ballpark,
    # otherwise convert from inches as a last resort.
    return round(val if val >= lo else inch_as_cm)


def _normalize_shoes(raw):
    """Shoe size -> millimetres. Accepts "285mm", "285", EU sizes like "42"/"42eu",
    and dual "285/42" (first wins). Returns 0 when unusable."""
    import re

    if raw is None:
        return 0
    s = str(raw).strip().lower()
    if not s:
        return 0
    if "/" in s:
        s = s.split("/", 1)[0].strip()

    num = re.search(r"-?\d+(?:\.\d+)?", s)
    if not num:
        return 0
    val = float(num.group())

    if "mm" in s or val >= 150:
        return round(val)                 # already millimetres
    if "cm" in s:
        return round(val * 10)
    # Bare small number -> EU size. EU 42 ~= 270mm foot length.
    if 30 <= val <= 55:
        return round(val * 20.0 / 3.0 - 10)
    return round(val)


def _extract_local_embedding(path):
    """Face embedding from a local image file, normalized to match search."""
    try:
        import numpy as np
        comparator = get_face_comparator()
        emb, _ = comparator.extract_face_embedding_optimized(path)
        if emb is None:
            return None
        emb = emb.astype("float32")
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb.tobytes()
    except Exception as e:
        print(f"[RosterImport] embedding failed for {path}: {e}")
        return None


def _process_roster_upload(csv_file, zip_file, agency_name):
    """Parse an uploaded CSV roster + optional ZIP of photos, saving each model.
    Photos are matched to rows by slug(name) == slug(photo filename). Returns
    the number of models imported."""
    import csv as _csv
    import io
    import zipfile

    # 1) Unpack photos from the ZIP (if provided) into static/model_photos,
    #    keyed by slug so we can match them to CSV rows by name.
    photo_by_slug = {}
    if zip_file and zip_file.filename:
        os.makedirs(PHOTO_DIR, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_file) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    fname = os.path.basename(info.filename)
                    base, ext = os.path.splitext(fname)
                    if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                        continue
                    slug = _slug(base)
                    if not slug:
                        continue
                    out_name = f"{slug}{ext.lower()}"
                    out_path = os.path.join(PHOTO_DIR, out_name)
                    with zf.open(info) as src, open(out_path, "wb") as dst:
                        dst.write(src.read())
                    photo_by_slug[slug] = out_name
        except Exception as e:
            print(f"[RosterImport] could not read ZIP: {e}")

    # 2) Parse the CSV and upsert each model.
    raw = csv_file.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig", errors="replace")
    reader = _csv.DictReader(io.StringIO(raw))

    imported = 0
    for row in reader:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        slug = _slug(name)

        # Accept both the new unit-agnostic column names and the older
        # *_cm / *_inch / *_mm names, whichever the agency's CSV happens to use.
        def col(*names):
            for n in names:
                v = row.get(n)
                if v is not None and str(v).strip():
                    return v
            return ""

        photo_url = ""
        face_embedding = None
        if slug in photo_by_slug:
            photo_url = f"/static/model_photos/{photo_by_slug[slug]}"
            face_embedding = _extract_local_embedding(os.path.join(PHOTO_DIR, photo_by_slug[slug]))

        model = {
            "english": name,
            "korean": (row.get("korean_name") or "").strip(),
            "birth": _to_int(row.get("birth_year"), 1995),
            "gender": (row.get("gender") or "").strip().lower() or "female",
            "nationality": (row.get("nationality") or "other").strip().lower(),
            "height": _normalize_measurement(col("height", "height_cm"), "height"),
            "waist": _normalize_measurement(col("waist", "waist_cm", "waist_inch"), "waist"),
            "chest": _normalize_measurement(col("chest", "chest_cm", "bust", "bust_cm"), "chest"),
            "hips": _normalize_measurement(col("hips", "hips_cm"), "hips"),
            "shoes": _normalize_shoes(col("shoes", "shoes_mm", "shoe", "shoe_mm")),
            "hair_color": (row.get("hair") or "black").strip().lower(),
            "eye_color": (row.get("eyes") or "brown").strip().lower(),
            "rate": _to_int(row.get("rate_usd")),
            "photo_url": photo_url,
            "workTypes": [],
            "looks": [],
        }
        if database.upsert_model(model, agency_name, face_embedding):
            imported += 1

    return imported


@app.route("/model_template.csv")
def model_template():
    from flask import Response
    header = ",".join(CSV_TEMPLATE_COLUMNS)
    # Two examples on purpose: one typed in cm/mm, one typed in inches/EU, to
    # show agencies they can use either — the importer normalizes both.
    example_cm = "Kim Jae Young,김재영,1998,male,korean,186,98,78,89,280,black,brown,3000"
    example_in = "Jane Doe,제인도우,1999,female,korean,5'9,34in,28in,35in,42eu,brown,brown,2500"
    csv_body = header + "\n" + example_cm + "\n" + example_in + "\n"
    return Response(
        csv_body,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=model_template.csv"},
    )


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

    # Optional: agency uploaded a CSV roster (+ optional photo ZIP). If present,
    # we import it as the primary source; the crawler then only handles future
    # updates. If absent, we'll crawl their website instead.
    imported = 0
    csv_file = request.files.get("rosterCsv")
    zip_file = request.files.get("photosZip")
    if csv_file and csv_file.filename:
        try:
            imported = _process_roster_upload(csv_file, zip_file, agency_name)
        except Exception as e:
            print(f"[RosterImport] failed: {e}")
            return jsonify({"error": f"Agency saved, but roster import failed: {e}"}), 500

    msg = "Agency registered"
    if imported:
        msg += f" — imported {imported} model(s)"
    return jsonify({"status": "ok", "message": msg, "imported": imported})


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


@app.route("/admin/delete-agency/<int:agency_id>", methods=["POST"])
def admin_delete_agency(agency_id):
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 401
    name, deleted = database.delete_agency(agency_id)
    if name is None:
        return jsonify({"error": "Agency not found"}), 404
    return jsonify({"status": "ok", "agency": name, "models_deleted": deleted})


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


@app.route("/admin/sync-all", methods=["POST"])
def admin_sync_all():
    """Re-crawl every agency whose last crawl is older than 90 days (or never
    crawled) — the quarterly maintenance pass. Runs them one after another in a
    background thread so the request returns immediately."""
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 401

    import asyncio
    from datetime import datetime, timedelta
    from crawler import crawl_agency

    cutoff = datetime.now() - timedelta(days=90)
    conn = database.get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM agencies "
            "WHERE last_crawled_at IS NULL OR last_crawled_at < %s",
            (cutoff,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return jsonify({"status": "ok", "count": 0,
                        "message": "All agencies are up to date (crawled within 90 days)."})

    def do_crawl_all():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for agency in rows:
            try:
                loop.run_until_complete(crawl_agency(agency))
            except Exception as e:
                print(f"[SyncAll] {agency.get('agency_name')} failed: {e}")
        loop.close()

    t = threading.Thread(target=do_crawl_all, daemon=True)
    t.start()
    names = ", ".join(a["agency_name"] for a in rows)
    return jsonify({"status": "ok", "count": len(rows),
                    "message": f"Syncing {len(rows)} agency(ies) due for update: {names}"})



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


@app.route("/admin/model", methods=["GET"])
def admin_model_get():
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 401
    model_id = request.args.get("id", "")
    if not model_id:
        return jsonify({"error": "Missing id"}), 400
    model = database.get_model(model_id)
    if model is None:
        return jsonify({"error": "Model not found"}), 404
    return jsonify(model)


@app.route("/admin/model", methods=["POST"])
def admin_model_update():
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True) or {}
    model_id = data.pop("id", "")
    if not model_id:
        return jsonify({"error": "Missing id"}), 400
    int_fields = {"birth", "height", "chest", "waist", "hips", "shoes", "rate", "active"}
    fields = {}
    for k, v in data.items():
        if k in int_fields:
            try:
                fields[k] = int(v) if v not in (None, "") else None
            except (ValueError, TypeError):
                fields[k] = None
        else:
            fields[k] = v
    updated = database.update_model(model_id, fields)
    if not updated:
        return jsonify({"error": "Model not found or nothing changed"}), 404
    return jsonify({"status": "ok"})


@app.route("/book", methods=["POST"])
def book_model():
    data = request.get_json(force=True)
    model_name  = data.get("model_name", "")
    agency_name = data.get("agency_name", "")
    client_name  = data.get("client_name", "").strip()
    client_email = data.get("client_email", "").strip()
    client_phone = data.get("client_phone", "").strip()
    notes        = data.get("notes", "").strip()

    if not client_name or not client_email:
        return jsonify({"error": "Missing required fields"}), 400

    cfg = database.load_config()
    gmail_user = cfg.get("gmail_user", "")
    gmail_pass = cfg.get("gmail_app_password", "")
    notify_email = cfg.get("notify_email", gmail_user)

    model_id = data.get("model_id", "")
    database.save_booking(model_id, model_name, agency_name, client_name, client_email, client_phone, notes)

    if not gmail_user or not gmail_pass:
        print(f"[BOOKING] {client_name} <{client_email}> wants to book {model_name} ({agency_name}). Notes: {notes}")
        return jsonify({"status": "ok"})

    subject = f"Booking Request — {model_name}"
    body = f"""New booking request from Model Matching

Model:   {model_name}
Agency:  {agency_name}

Client:  {client_name}
Email:   {client_email}
Phone:   {client_phone or '—'}

Notes:
{notes or '—'}
"""
    try:
        msg = MIMEMultipart()
        msg["From"] = gmail_user
        msg["To"] = notify_email
        msg["Subject"] = subject
        msg["Reply-To"] = client_email
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, notify_email, msg.as_string())
    except Exception as e:
        print(f"[BOOKING] Email send failed: {e}")
        return jsonify({"error": "Email failed"}), 500

    return jsonify({"status": "ok"})


@app.route("/admin/bookings")
def admin_bookings():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    bookings = database.get_bookings()
    return render_template("admin_bookings.html", bookings=bookings)


if __name__ == "__main__":
    app.run(debug=True)
