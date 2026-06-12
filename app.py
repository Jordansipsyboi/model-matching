from flask import Flask, render_template, request, jsonify

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/find-models")
def find_models():
    return render_template("find-models.html")


@app.route("/list-models")
def list_models():
    return render_template("list-models.html")


@app.route("/api/submit-agency", methods=["POST"])
def submit_agency():
    agency_name = request.form.get("agencyName", "").strip()
    contact_name = request.form.get("contactName", "").strip()
    contact_email = request.form.get("contactEmail", "").strip()
    market = request.form.get("agencyMarket", "").strip()

    if not all([agency_name, contact_name, contact_email, market]):
        return jsonify({"error": "Missing required fields"}), 400

    # TODO: persist to database / send notification email
    return jsonify({"status": "ok", "message": "Listing received"})


if __name__ == "__main__":
    app.run(debug=True)
