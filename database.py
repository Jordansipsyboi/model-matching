import json
import os

import pymysql
import pymysql.cursors

_cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
with open(_cfg_path) as _f:
    _cfg = json.load(_f)

def load_config():
    with open(_cfg_path) as f:
        return json.load(f)

DB_HOST = _cfg["db_host"]
DB_PORT = int(_cfg["db_port"])
DB_USER = _cfg["db_user"]
DB_PASS = _cfg["db_pass"]
DB_NAME = _cfg["db_name"]


def _cm_to_ft(cm):
    inches_total = cm / 2.54
    feet = int(inches_total // 12)
    inches = round(inches_total % 12, 1)
    return f"{feet}'{inches}\""


def _cm_to_in(cm):
    return round(cm / 2.54, 1)


def _mm_to_eu(mm):
    eu = (mm / 10 + 1.5) / 0.667
    return round(eu)


SEED_MODELS = [
    {"id": "park_jae_geun",  "korean": "박재근",   "english": "PARK JAE GEUN",  "birth": 1989, "height": 184, "chest": 77, "waist": 66, "hips": 88, "shoes": 270, "hair_length": "medium", "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["commercial","lookbook","ecommerce"],          "looks": ["clean","classic"],       "rate": 3800},
    {"id": "cho_min_ho",     "korean": "조민호",   "english": "CHO MIN HO",     "birth": 1989, "height": 189, "chest": 80, "waist": 68, "hips": 91, "shoes": 285, "hair_length": "medium", "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["runway","editorial","campaign"],               "looks": ["highfashion","clean"],   "rate": 5300},
    {"id": "kim_jae_young",  "korean": "김재영",   "english": "KIM JAE YOUNG",  "birth": 1988, "height": 186, "chest": 78, "waist": 68, "hips": 89, "shoes": 280, "hair_length": "medium", "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["commercial","campaign","lookbook"],           "looks": ["classic","natural"],     "rate": 3400},
    {"id": "lee_sun_ki",     "korean": "이선기",   "english": "LEE SUN KI",     "birth": 1988, "height": 188, "chest": 79, "waist": 68, "hips": 90, "shoes": 280, "hair_length": "medium", "hair_color": "black", "eye_color": "dark brown", "gender": "male", "nationality": "korean", "workTypes": ["runway","editorial","campaign"],               "looks": ["highfashion","edgy"],    "rate": 12600},
    {"id": "shin_ji_hoon",   "korean": "신지훈",   "english": "SHIN JI HOON",   "birth": 1988, "height": 187, "chest": 78, "waist": 68, "hips": 89, "shoes": 265, "hair_length": "medium", "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["commercial","ecommerce","social"],            "looks": ["natural","clean"],       "rate": 2500},
    {"id": "kim_myung_joon", "korean": "김명준",   "english": "KIM MYUNG JOON", "birth": 1987, "height": 189, "chest": 80, "waist": 67, "hips": 91, "shoes": 275, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["runway","editorial"],                         "looks": ["highfashion","edgy"],    "rate": 9100},
    {"id": "tae_eun",        "korean": "태은",     "english": "TAE EUN",        "birth": 1991, "height": 188, "chest": 79, "waist": 66, "hips": 90, "shoes": 275, "hair_length": "buzzcut","hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["runway","editorial","campaign"],               "looks": ["highfashion","clean"],   "rate": 5300},
    {"id": "jung_dong_kyu",  "korean": "정동규",   "english": "JUNG DONG KYU",  "birth": 1996, "height": 186, "chest": 78, "waist": 66, "hips": 89, "shoes": 270, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["editorial","social","lookbook"],              "looks": ["clean","natural"],       "rate": 4500},
    {"id": "ahn_seung_joon", "korean": "안승준",   "english": "AHN SEUNG JOON", "birth": 1996, "height": 189, "chest": 80, "waist": 66, "hips": 91, "shoes": 265, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["runway","campaign","editorial"],               "looks": ["highfashion","edgy"],    "rate": 10900},
    {"id": "oliver_chang",   "korean": "올리버 장","english": "OLIVER CHANG",   "birth": 1991, "height": 184, "chest": 77, "waist": 68, "hips": 89, "shoes": 280, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "american", "workTypes": ["commercial","ecommerce","social"],            "looks": ["classic","natural"],     "rate": 3500},
    {"id": "cha_chi_eung",   "korean": "차치응",   "english": "CHA CHI EUNG",   "birth": 1988, "height": 187, "chest": 79, "waist": 70, "hips": 92, "shoes": 270, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["commercial","event","lookbook"],              "looks": ["athletic","classic"],    "rate": 400},
    {"id": "lee_ui_soo",     "korean": "이의수",   "english": "LEE UI SOO",     "birth": 1995, "height": 189, "chest": 80, "waist": 67, "hips": 91, "shoes": 270, "hair_length": "medium", "hair_color": "black", "eye_color": "dark brown", "gender": "male", "nationality": "korean", "workTypes": ["runway","editorial","campaign"],               "looks": ["highfashion","clean"],   "rate": 11700},
    {"id": "lee_yong_jun",   "korean": "이용준",   "english": "LEE YONG JUN",   "birth": 1991, "height": 188, "chest": 79, "waist": 67, "hips": 90, "shoes": 260, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["editorial","campaign","lookbook"],            "looks": ["edgy","highfashion"],    "rate": 3000},
    {"id": "kim_jong_hoon",  "korean": "김종훈",   "english": "KIM JONG HOON",  "birth": 1992, "height": 186, "chest": 78, "waist": 67, "hips": 89, "shoes": 270, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["commercial","ecommerce","social"],            "looks": ["clean","natural"],       "rate": 3300},
    {"id": "choi_jung_jin",  "korean": "최정진",   "english": "CHOI JUNG JIN",  "birth": 1986, "height": 185, "chest": 78, "waist": 68, "hips": 90, "shoes": 280, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["commercial","campaign","event"],              "looks": ["classic","natural"],     "rate": 3000},
    {"id": "ha_dong_joo",    "korean": "하동주",   "english": "HA DONG JOO",    "birth": 1995, "height": 186, "chest": 78, "waist": 67, "hips": 89, "shoes": 280, "hair_length": "buzzcut","hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["ecommerce","social","lookbook"],              "looks": ["clean","natural"],       "rate": 700},
    {"id": "lee_si_hyeong",  "korean": "이시형",   "english": "LEE SI HYEONG",  "birth": 1996, "height": 186, "chest": 77, "waist": 65, "hips": 88, "shoes": 260, "hair_length": "medium", "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["runway","editorial"],                         "looks": ["highfashion","edgy"],    "rate": 3400},
    {"id": "ryu_hyung_yeol", "korean": "류형열",   "english": "RYU HYUNG YEOL", "birth": 1991, "height": 188, "chest": 79, "waist": 66, "hips": 90, "shoes": 280, "hair_length": "medium", "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["runway","campaign","editorial"],               "looks": ["highfashion","clean"],   "rate": 8800},
    {"id": "yoon_jung_jae",  "korean": "윤정재",   "english": "YOON JUNG JAE",  "birth": 1996, "height": 184, "chest": 77, "waist": 66, "hips": 88, "shoes": 280, "hair_length": "buzzcut","hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["social","ecommerce","lookbook"],              "looks": ["clean","natural"],       "rate": 900},
    {"id": "jung_hyuk",      "korean": "정혁",     "english": "JUNG HYUK",      "birth": 1991, "height": 183, "chest": 79, "waist": 67, "hips": 90, "shoes": 275, "hair_length": "medium", "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["commercial","ecommerce","event"],             "looks": ["athletic","classic"],    "rate": 3500},
    {"id": "jung_yong_jin",  "korean": "정용진",   "english": "JUNG YONG JIN",  "birth": 1990, "height": 181, "chest": 78, "waist": 68, "hips": 89, "shoes": 270, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["commercial","event","social"],                "looks": ["natural","classic"],     "rate": 300},
    {"id": "kim_byung_seok", "korean": "김병석",   "english": "KIM BYUNG SEOK", "birth": 1994, "height": 183, "chest": 77, "waist": 66, "hips": 88, "shoes": 260, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["ecommerce","social","lookbook"],              "looks": ["clean","natural"],       "rate": 400},
    {"id": "kim_kyung_dae",  "korean": "김경대",   "english": "KIM KYUNG DAE",  "birth": 1991, "height": 185, "chest": 78, "waist": 66, "hips": 89, "shoes": 265, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["editorial","lookbook","campaign"],            "looks": ["clean","edgy"],          "rate": 2800},
    {"id": "kim_hyun_woo",   "korean": "김현우",   "english": "KIM HYUN WOO",   "birth": 1990, "height": 185, "chest": 79, "waist": 67, "hips": 90, "shoes": 280, "hair_length": "medium", "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["commercial","campaign","ecommerce"],          "looks": ["athletic","classic"],    "rate": 1700},
    {"id": "kim_hyun_jung",  "korean": "김현중",   "english": "KIM HYUN JUNG",  "birth": 1991, "height": 186, "chest": 78, "waist": 66, "hips": 89, "shoes": 270, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["editorial","runway","campaign"],              "looks": ["highfashion","edgy"],    "rate": 6800},
    {"id": "byun_hee_sang",  "korean": "변희상",   "english": "BYUN HEE SANG",  "birth": 1996, "height": 186, "chest": 77, "waist": 66, "hips": 88, "shoes": 270, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["social","ecommerce","lookbook"],              "looks": ["clean","natural"],       "rate": 600},
    {"id": "lim_chae_woong", "korean": "임채웅",   "english": "LIM CHAE WOONG", "birth": 1996, "height": 189, "chest": 80, "waist": 68, "hips": 91, "shoes": 280, "hair_length": "short",  "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["runway","editorial","campaign"],              "looks": ["highfashion","clean"],   "rate": 6800},
    {"id": "jang_sung_hoon", "korean": "장성훈",   "english": "JANG SUNG HOON", "birth": 1992, "height": 185, "chest": 78, "waist": 67, "hips": 89, "shoes": 280, "hair_length": "medium", "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "korean",   "workTypes": ["commercial","ecommerce","lookbook"],          "looks": ["classic","natural"],     "rate": 2200},
    {"id": "model_29",       "korean": "",         "english": "MODEL",          "birth": 1990, "height": 185, "chest": 78, "waist": 67, "hips": 89, "shoes": 270, "hair_length": "medium", "hair_color": "black", "eye_color": "brown", "gender": "male",   "nationality": "other",    "workTypes": ["commercial","ecommerce"],                     "looks": ["clean","natural"],       "rate": 4700},
]


def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def init_db():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agencies (
                id              INT AUTO_INCREMENT PRIMARY KEY,
                agency_name     VARCHAR(255) NOT NULL,
                agency_website  VARCHAR(500) NOT NULL,
                contact_name    VARCHAR(255) NOT NULL,
                contact_email   VARCHAR(255) NOT NULL,
                market          VARCHAR(100) NOT NULL,
                notes           TEXT,
                submitted_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_crawled_at DATETIME DEFAULT NULL
            ) CHARACTER SET utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id             VARCHAR(255) PRIMARY KEY,
                korean         VARCHAR(255),
                english        VARCHAR(255),
                birth          INT,
                height         INT,
                chest          INT,
                waist          INT,
                hips           INT,
                shoes          INT,
                hair_length    VARCHAR(100),
                hair_color     VARCHAR(100),
                eye_color      VARCHAR(100),
                gender         VARCHAR(50),
                nationality    VARCHAR(100),
                work_types     JSON,
                looks          JSON,
                rate           INT,
                photo_url      TEXT,
                agency_name    VARCHAR(255),
                profile_url    TEXT,
                face_embedding LONGBLOB DEFAULT NULL,
                face_gender    VARCHAR(1) DEFAULT NULL,
                face_age       TINYINT UNSIGNED DEFAULT NULL,
                active         TINYINT(1) DEFAULT 1
            ) CHARACTER SET utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                model_id     VARCHAR(255),
                model_name   VARCHAR(255),
                agency_name  VARCHAR(255),
                client_name  VARCHAR(255),
                client_email VARCHAR(255),
                client_phone VARCHAR(100),
                notes        TEXT,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            ) CHARACTER SET utf8mb4
        """)
    conn.commit()
    conn.close()
    ensure_face_embedding_column()
    ensure_active_column()
    ensure_face_gender_age_columns()
    ensure_active_column()


def seed_db():
    conn = get_connection()
    with conn.cursor() as cur:
        for m in SEED_MODELS:
            cur.execute(
                """
                INSERT INTO models
                    (id, korean, english, birth, height, chest, waist, hips, shoes,
                     hair_length, hair_color, eye_color, gender, nationality,
                     work_types, looks, rate)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE id=id
                """,
                (
                    m["id"], m["korean"], m["english"], m["birth"],
                    m["height"], m["chest"], m["waist"], m["hips"], m["shoes"],
                    m["hair_length"], m["hair_color"], m["eye_color"],
                    m["gender"], m["nationality"],
                    json.dumps(m["workTypes"]), json.dumps(m["looks"]), m["rate"],
                ),
            )
    conn.commit()
    conn.close()


def _row_to_model(row):
    h = row["height"] or 0
    chest = row["chest"] or 0
    waist = row["waist"] or 0
    hips = row["hips"] or 0
    shoes = row["shoes"] or 0

    work_types = row.get("work_types") or "[]"
    looks = row.get("looks") or "[]"
    if isinstance(work_types, list):
        work_types_list = work_types
    else:
        work_types_list = json.loads(work_types)
    if isinstance(looks, list):
        looks_list = looks
    else:
        looks_list = json.loads(looks)

    return {
        "id": row["id"],
        "korean": row["korean"],
        "english": row["english"],
        "birth": row["birth"],
        "gender": row["gender"],
        "nationality": row["nationality"],
        "hair_length": row["hair_length"],
        "hair_color": row["hair_color"],
        "eye_color": row["eye_color"],
        "workTypes": work_types_list,
        "looks": looks_list,
        "rate": row["rate"],
        "photo_url": row["photo_url"] or "",
        "agency_name": row["agency_name"] or "",
        "profile_url": row["profile_url"] or "",
        "agency_email": row.get("agency_email") or "",
        "agency_website_url": row.get("agency_website_url") or "",
        # metric
        "height": h,
        "chest": chest,
        "waist": waist,
        "hips": hips,
        "shoes": shoes,
        # imperial / EU
        "height_imperial": _cm_to_ft(h) if h else "",
        "chest_in": _cm_to_in(chest) if chest else "",
        "waist_in": _cm_to_in(waist) if waist else "",
        "hips_in": _cm_to_in(hips) if hips else "",
        "shoes_eu": _mm_to_eu(shoes) if shoes else "",
    }


def save_agency(agency_name, agency_website, contact_name, contact_email, market, notes):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agencies (agency_name, agency_website, contact_name, contact_email, market, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (agency_name, agency_website, contact_name, contact_email, market, notes),
        )
    conn.commit()
    conn.close()


def get_agency(agency_id):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM agencies WHERE id = %s", (agency_id,))
        row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_agency_by_website(host):
    """Find a registered agency whose website matches the given host (case-insensitive,
    ignores scheme/www/path). Returns the agency dict or None.
    Used so a manual URL crawl reuses the agency the user already registered,
    instead of creating an orphaned record under a different name."""
    host = (host or "").lower().replace("www.", "").strip("/")
    if not host:
        return None
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM agencies")
        rows = cur.fetchall()
    conn.close()
    for r in rows:
        site = (r.get("agency_website") or "").lower()
        # normalize stored website to a bare host for comparison
        site = site.replace("https://", "").replace("http://", "").replace("www.", "").strip("/")
        site_host = site.split("/")[0]
        if site_host and (site_host == host or host in site_host or site_host in host):
            return dict(r)
    return None


def delete_agency(agency_id):
    """Delete an agency and all of its models. Returns (agency_name, models_deleted)
    or (None, 0) if the agency didn't exist."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT agency_name FROM agencies WHERE id = %s", (agency_id,))
            row = cur.fetchone()
            if not row:
                return None, 0
            agency_name = row["agency_name"]
            cur.execute("DELETE FROM models WHERE agency_name = %s", (agency_name,))
            models_deleted = cur.rowcount
            cur.execute("DELETE FROM agencies WHERE id = %s", (agency_id,))
        conn.commit()
        return agency_name, models_deleted
    finally:
        conn.close()


def upsert_model(m: dict, agency_name: str, face_embedding=None):
    """Insert or update a single model (used by the CSV/ZIP roster import).
    Mirrors the crawler's save logic so manually-uploaded rosters and crawled
    rosters live in the same shape. Matched by a slug id from the english name,
    so re-uploading the same roster updates rather than duplicates."""
    import re as _re
    if not m.get("english"):
        return False
    model_id = _re.sub(r"[^a-z0-9]+", "_", m["english"].lower()).strip("_")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO models
                    (id, korean, english, birth, height, chest, waist, hips, shoes,
                     hair_length, hair_color, eye_color, gender, nationality,
                     work_types, looks, rate, photo_url, agency_name, profile_url,
                     face_embedding, active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    korean=VALUES(korean), english=VALUES(english), birth=VALUES(birth),
                    height=VALUES(height), chest=VALUES(chest), waist=VALUES(waist),
                    hips=VALUES(hips), shoes=VALUES(shoes), hair_length=VALUES(hair_length),
                    hair_color=VALUES(hair_color), eye_color=VALUES(eye_color),
                    gender=VALUES(gender), nationality=VALUES(nationality),
                    work_types=VALUES(work_types), looks=VALUES(looks), rate=VALUES(rate),
                    photo_url=VALUES(photo_url), agency_name=VALUES(agency_name),
                    profile_url=VALUES(profile_url), active=1,
                    face_embedding=IF(VALUES(face_embedding) IS NOT NULL, VALUES(face_embedding), face_embedding)
                """,
                (
                    model_id,
                    m.get("korean", ""),
                    m["english"],
                    m.get("birth", 1995),
                    m.get("height", 0),
                    m.get("chest", 0),
                    m.get("waist", 0),
                    m.get("hips", 0),
                    m.get("shoes", 0),
                    m.get("hair_length", "medium"),
                    m.get("hair_color", "black"),
                    m.get("eye_color", "brown"),
                    m.get("gender", "female"),
                    m.get("nationality", "other"),
                    json.dumps(m.get("workTypes", [])),
                    json.dumps(m.get("looks", [])),
                    m.get("rate", 0),
                    m.get("photo_url", ""),
                    agency_name,
                    m.get("profile_url", ""),
                    face_embedding,
                ),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def get_all_agencies():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT a.*, COUNT(m.id) as model_count
            FROM agencies a
            LEFT JOIN models m ON m.agency_name = a.agency_name
            GROUP BY a.id
            ORDER BY a.submitted_at DESC
        """)
        rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        for col in ("submitted_at", "last_crawled_at"):
            if d.get(col) and hasattr(d[col], "isoformat"):
                d[col] = d[col].isoformat()
        result.append(d)
    return result


def get_all_models(active_only=False):
    conn = get_connection()
    with conn.cursor() as cur:
        where = "WHERE m.active = 1" if active_only else ""
        cur.execute(f"""
            SELECT m.*, a.contact_email as agency_email, a.agency_website as agency_website_url
            FROM models m
            LEFT JOIN agencies a ON a.agency_name = m.agency_name
            {where}
        """)
        rows = cur.fetchall()
    conn.close()
    return [_row_to_model(r) for r in rows]


def get_existing_profile_urls(agency_name):
    """Map profile_url -> model dict for models already crawled for this agency.
    Used to skip re-crawling people we've already extracted on a previous run."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM models WHERE agency_name = %s AND profile_url != '' AND active = 1",
            (agency_name,),
        )
        rows = cur.fetchall()
    conn.close()
    return {r["profile_url"]: _row_to_model(r) for r in rows}


def set_models_active(ids, active=True):
    if not ids:
        return
    conn = get_connection()
    with conn.cursor() as cur:
        placeholders = ",".join(["%s"] * len(ids))
        cur.execute(
            f"UPDATE models SET active = %s WHERE id IN ({placeholders})",
            [1 if active else 0, *ids],
        )
    conn.commit()
    conn.close()


def get_models_for_search(filters: dict) -> list:
    """Return models matching filter criteria, including raw face_embedding bytes."""
    conditions = ["m.active = 1"]
    params = []

    if filters.get("gender"):
        placeholders = ",".join(["%s"] * len(filters["gender"]))
        conditions.append(f"m.gender IN ({placeholders})")
        params.extend(filters["gender"])
    if filters.get("height_min") is not None:
        conditions.append("m.height >= %s"); params.append(filters["height_min"])
    if filters.get("height_max") is not None:
        conditions.append("m.height <= %s"); params.append(filters["height_max"])
    if filters.get("waist_min") is not None:
        conditions.append("m.waist >= %s"); params.append(filters["waist_min"])
    if filters.get("waist_max") is not None:
        conditions.append("m.waist <= %s"); params.append(filters["waist_max"])
    if filters.get("chest_min") is not None:
        conditions.append("m.chest >= %s"); params.append(filters["chest_min"])
    if filters.get("chest_max") is not None:
        conditions.append("m.chest <= %s"); params.append(filters["chest_max"])
    if filters.get("hips_min") is not None:
        conditions.append("m.hips >= %s"); params.append(filters["hips_min"])
    if filters.get("hips_max") is not None:
        conditions.append("m.hips <= %s"); params.append(filters["hips_max"])
    if filters.get("nationalities"):
        placeholders = ",".join(["%s"] * len(filters["nationalities"]))
        conditions.append(f"m.nationality IN ({placeholders})")
        params.extend(filters["nationalities"])
    if filters.get("hair_lengths"):
        placeholders = ",".join(["%s"] * len(filters["hair_lengths"]))
        conditions.append(f"m.hair_length IN ({placeholders})")
        params.extend(filters["hair_lengths"])
    if filters.get("hair_colors"):
        placeholders = ",".join(["%s"] * len(filters["hair_colors"]))
        conditions.append(f"m.hair_color IN ({placeholders})")
        params.extend(filters["hair_colors"])
    if filters.get("eye_colors"):
        placeholders = ",".join(["%s"] * len(filters["eye_colors"]))
        conditions.append(f"m.eye_color IN ({placeholders})")
        params.extend(filters["eye_colors"])
    if filters.get("age_min") is not None:
        max_birth = 2026 - filters["age_min"]
        conditions.append("m.birth <= %s"); params.append(max_birth)
    if filters.get("age_max") is not None:
        min_birth = 2026 - filters["age_max"]
        conditions.append("m.birth >= %s"); params.append(min_birth)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT m.*, a.contact_email as agency_email, a.agency_website as agency_website_url
        FROM models m
        LEFT JOIN agencies a ON a.agency_name = m.agency_name
        {where}
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        model = _row_to_model(r)
        model["_face_embedding"] = r.get("face_embedding")  # raw bytes, not serialized
        results.append(model)
    return results


_EDITABLE_COLUMNS = {
    "english", "korean", "birth", "gender", "nationality",
    "height", "chest", "waist", "hips", "shoes",
    "hair_length", "hair_color", "eye_color", "rate", "active",
}


def get_model(model_id):
    """Return a dict of editable fields for a single model, or None if not found."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, english, korean, birth, gender, nationality, "
                "height, chest, waist, hips, shoes, hair_length, hair_color, "
                "eye_color, rate, active FROM models WHERE id = %s",
                (model_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_model(model_id, fields: dict):
    """Update only the allowed editable columns for a model.
    Unknown or disallowed column names are silently ignored."""
    safe = {k: v for k, v in fields.items() if k in _EDITABLE_COLUMNS}
    if not safe:
        return False
    set_clause = ", ".join(f"{col} = %s" for col in safe)
    values = list(safe.values()) + [model_id]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE models SET {set_clause} WHERE id = %s",
                values,
            )
            conn.commit()
            return cur.rowcount > 0
    finally:
        conn.close()


def ensure_active_column():
    """Add active column to models table if it doesn't exist yet (migration safety net)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as cnt FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'models' AND COLUMN_NAME = 'active'
            """, (DB_NAME,))
            if cur.fetchone()["cnt"] == 0:
                cur.execute("ALTER TABLE models ADD COLUMN active TINYINT(1) DEFAULT 1")
                conn.commit()
    finally:
        conn.close()


def ensure_face_embedding_column():
    """Add face_embedding column to models table if it doesn't exist yet."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as cnt FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'models' AND COLUMN_NAME = 'face_embedding'
            """, (DB_NAME,))
            if cur.fetchone()["cnt"] == 0:
                cur.execute("ALTER TABLE models ADD COLUMN face_embedding LONGBLOB DEFAULT NULL")
                conn.commit()
    finally:
        conn.close()


def ensure_face_gender_age_columns():
    """Add face_gender and face_age columns if they don't exist (migration for existing DBs)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for col, definition in [
                ("face_gender", "VARCHAR(1) DEFAULT NULL"),
                ("face_age",    "TINYINT UNSIGNED DEFAULT NULL"),
            ]:
                cur.execute("""
                    SELECT COUNT(*) as cnt FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'models' AND COLUMN_NAME = %s
                """, (DB_NAME, col))
                if cur.fetchone()["cnt"] == 0:
                    cur.execute(f"ALTER TABLE models ADD COLUMN {col} {definition}")
            conn.commit()
    finally:
        conn.close()


def save_booking(model_id, model_name, agency_name, client_name, client_email, client_phone, notes):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO bookings
               (model_id, model_name, agency_name, client_name, client_email, client_phone, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (model_id, model_name, agency_name, client_name, client_email, client_phone, notes)
        )
    conn.commit()
    conn.close()


def get_bookings():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM bookings ORDER BY created_at DESC")
        rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    seed_db()
    count = len(get_all_models())
    print(f"MySQL database ready with {count} models.")
