from flask import Flask, render_template, request, jsonify

import database

app = Flask(__name__)

# Make sure the database file exists and has the starter models in it.
database.init_db()
database.seed_db()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/find-models")
def find_models():
    return render_template("find-models.html")


@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.route("/list-models")
def list_models():
    return render_template("list-models.html")


@app.route("/api/models")
def api_models():
    """Return every model in the database as JSON."""
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


if __name__ == "__main__":
    app.run(debug=True)
