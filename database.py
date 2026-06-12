import json
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "models.db")


def _cm_to_ft(cm):
    inches_total = cm / 2.54
    feet = int(inches_total // 12)
    inches = round(inches_total % 12, 1)
    return f"{feet}'{inches}\""


def _cm_to_in(cm):
    return round(cm / 2.54, 1)


def _mm_to_eu(mm):
    # EU size = (foot length in cm + 1.5) / 0.667
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agencies (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            agency_name     TEXT NOT NULL,
            agency_website  TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            contact_email   TEXT NOT NULL,
            market          TEXT NOT NULL,
            notes           TEXT,
            submitted_at    TEXT DEFAULT (datetime('now')),
            last_crawled_at TEXT DEFAULT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS models (
            id          TEXT PRIMARY KEY,
            korean      TEXT,
            english     TEXT,
            birth       INTEGER,
            height      INTEGER,
            chest       INTEGER,
            waist       INTEGER,
            hips        INTEGER,
            shoes       INTEGER,
            hair_length TEXT,
            hair_color  TEXT,
            eye_color   TEXT,
            gender      TEXT,
            nationality TEXT,
            work_types  TEXT,
            looks       TEXT,
            rate        INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def seed_db():
    conn = get_connection()
    for m in SEED_MODELS:
        conn.execute(
            """
            INSERT OR REPLACE INTO models
                (id, korean, english, birth, height, chest, waist, hips, shoes,
                 hair_length, hair_color, eye_color, gender, nationality,
                 work_types, looks, rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    h = row["height"]
    chest = row["chest"]
    waist = row["waist"]
    hips = row["hips"]
    shoes = row["shoes"]
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
        "workTypes": json.loads(row["work_types"]),
        "looks": json.loads(row["looks"]),
        "rate": row["rate"],
        # metric
        "height": h,
        "chest": chest,
        "waist": waist,
        "hips": hips,
        "shoes": shoes,
        # imperial / EU
        "height_imperial": _cm_to_ft(h),
        "chest_in": _cm_to_in(chest),
        "waist_in": _cm_to_in(waist),
        "hips_in": _cm_to_in(hips),
        "shoes_eu": _mm_to_eu(shoes),
    }


def save_agency(agency_name, agency_website, contact_name, contact_email, market, notes):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO agencies (agency_name, agency_website, contact_name, contact_email, market, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (agency_name, agency_website, contact_name, contact_email, market, notes),
    )
    conn.commit()
    conn.close()


def get_all_models():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM models").fetchall()
    conn.close()
    return [_row_to_model(r) for r in rows]


if __name__ == "__main__":
    # Delete and recreate the db so schema changes take effect
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    seed_db()
    count = len(get_all_models())
    print(f"Database ready at {DB_PATH} with {count} models.")
