import json
import os

import pymysql
import pymysql.cursors

_cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
with open(_cfg_path) as _f:
    _cfg = json.load(_f)

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
                id          VARCHAR(255) PRIMARY KEY,
                korean      VARCHAR(255),
                english     VARCHAR(255),
                birth       INT,
                height      INT,
                chest       INT,
                waist       INT,
                hips        INT,
                shoes       INT,
                hair_length VARCHAR(100),
                hair_color  VARCHAR(100),
                eye_color   VARCHAR(100),
                gender      VARCHAR(50),
                nationality VARCHAR(100),
                work_types  JSON,
                looks       JSON,
                rate        INT,
                photo_url   TEXT,
                agency_name VARCHAR(255),
                profile_url TEXT
            ) CHARACTER SET utf8mb4
        """)
    conn.commit()
    conn.close()


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


def get_all_models():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT m.*, a.contact_email as agency_email, a.agency_website as agency_website_url
            FROM models m
            LEFT JOIN agencies a ON a.agency_name = m.agency_name
        """)
        rows = cur.fetchall()
    conn.close()
    return [_row_to_model(r) for r in rows]


if __name__ == "__main__":
    init_db()
    seed_db()
    count = len(get_all_models())
    print(f"MySQL database ready with {count} models.")
