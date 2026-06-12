"""
Database layer for Model Matching.

Uses SQLite, which is just a single file (models.db) that lives in this
folder. No server to install. This module:
  1. Creates the `models` table if it doesn't exist
  2. Seeds it with the starter model data (the same 30 models that used to
     be hardcoded in find-models.html)
  3. Provides simple helper functions to read models back out

Run this file directly to (re)build the database:
    python database.py
"""

import json
import os
import sqlite3

# The database file sits right next to this script.
DB_PATH = os.path.join(os.path.dirname(__file__), "models.db")


# ---------------------------------------------------------------------------
# Starter data (migrated out of find-models.html so it lives in one place).
# workTypes and looks are lists, so we store them as JSON text in the DB.
# ---------------------------------------------------------------------------
SEED_MODELS = [
    {"id": "park_jae_geun", "korean": "박재근", "english": "PARK JAE GEUN", "birth": 1989, "height": 184, "waist": 30, "shoes": 270, "hair": "medium", "gender": "male", "nationality": "korean", "workTypes": ["commercial", "lookbook", "ecommerce"], "looks": ["clean", "classic"], "rate": 3800},
    {"id": "cho_min_ho", "korean": "조민호", "english": "CHO MIN HO", "birth": 1989, "height": 189, "waist": 29, "shoes": 285, "hair": "medium", "gender": "male", "nationality": "korean", "workTypes": ["runway", "editorial", "campaign"], "looks": ["highfashion", "clean"], "rate": 5300},
    {"id": "kim_jae_young", "korean": "김재영", "english": "KIM JAE YOUNG", "birth": 1988, "height": 186, "waist": 30, "shoes": 280, "hair": "medium", "gender": "male", "nationality": "korean", "workTypes": ["commercial", "campaign", "lookbook"], "looks": ["classic", "natural"], "rate": 3400},
    {"id": "lee_sun_ki", "korean": "이선기", "english": "LEE SUN KI", "birth": 1988, "height": 188, "waist": 30, "shoes": 280, "hair": "medium", "gender": "male", "nationality": "korean", "workTypes": ["runway", "editorial", "campaign"], "looks": ["highfashion", "edgy"], "rate": 12600},
    {"id": "shin_ji_hoon", "korean": "신지훈", "english": "SHIN JI HOON", "birth": 1988, "height": 187, "waist": 30, "shoes": 265, "hair": "medium", "gender": "male", "nationality": "korean", "workTypes": ["commercial", "ecommerce", "social"], "looks": ["natural", "clean"], "rate": 2500},
    {"id": "kim_myung_joon", "korean": "김명준", "english": "KIM MYUNG JOON", "birth": 1987, "height": 189, "waist": 29, "shoes": 275, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["runway", "editorial"], "looks": ["highfashion", "edgy"], "rate": 9100},
    {"id": "tae_eun", "korean": "태은", "english": "TAE EUN", "birth": 1991, "height": 188, "waist": 28, "shoes": 275, "hair": "buzzcut", "gender": "male", "nationality": "korean", "workTypes": ["runway", "editorial", "campaign"], "looks": ["highfashion", "clean"], "rate": 5300},
    {"id": "jung_dong_kyu", "korean": "정동규", "english": "JUNG DONG KYU", "birth": 1996, "height": 186, "waist": 28, "shoes": 270, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["editorial", "social", "lookbook"], "looks": ["clean", "natural"], "rate": 4500},
    {"id": "ahn_seung_joon", "korean": "안승준", "english": "AHN SEUNG JOON", "birth": 1996, "height": 189, "waist": 28, "shoes": 265, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["runway", "campaign", "editorial"], "looks": ["highfashion", "edgy"], "rate": 10900},
    {"id": "oliver_chang", "korean": "올리버 장", "english": "OLIVER CHANG", "birth": 1991, "height": 184, "waist": 30, "shoes": 280, "hair": "short", "gender": "male", "nationality": "american", "workTypes": ["commercial", "ecommerce", "social"], "looks": ["classic", "natural"], "rate": 3500},
    {"id": "cha_chi_eung", "korean": "차치응", "english": "CHA CHI EUNG", "birth": 1988, "height": 187, "waist": 31, "shoes": 270, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["commercial", "event", "lookbook"], "looks": ["athletic", "classic"], "rate": 400},
    {"id": "lee_ui_soo", "korean": "이의수", "english": "LEE UI SOO", "birth": 1995, "height": 189, "waist": 29, "shoes": 270, "hair": "medium", "gender": "male", "nationality": "korean", "workTypes": ["runway", "editorial", "campaign"], "looks": ["highfashion", "clean"], "rate": 11700},
    {"id": "lee_yong_jun", "korean": "이용준", "english": "LEE YONG JUN", "birth": 1991, "height": 188, "waist": 29, "shoes": 260, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["editorial", "campaign", "lookbook"], "looks": ["edgy", "highfashion"], "rate": 3000},
    {"id": "kim_jong_hoon", "korean": "김종훈", "english": "KIM JONG HOON", "birth": 1992, "height": 186, "waist": 29, "shoes": 270, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["commercial", "ecommerce", "social"], "looks": ["clean", "natural"], "rate": 3300},
    {"id": "choi_jung_jin", "korean": "최정진", "english": "CHOI JUNG JIN", "birth": 1986, "height": 185, "waist": 30, "shoes": 280, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["commercial", "campaign", "event"], "looks": ["classic", "natural"], "rate": 3000},
    {"id": "ha_dong_joo", "korean": "하동주", "english": "HA DONG JOO", "birth": 1995, "height": 186, "waist": 29, "shoes": 280, "hair": "buzzcut", "gender": "male", "nationality": "korean", "workTypes": ["ecommerce", "social", "lookbook"], "looks": ["clean", "natural"], "rate": 700},
    {"id": "lee_si_hyeong", "korean": "이시형", "english": "LEE SI HYEONG", "birth": 1996, "height": 186, "waist": 27, "shoes": 260, "hair": "medium", "gender": "male", "nationality": "korean", "workTypes": ["runway", "editorial"], "looks": ["highfashion", "edgy"], "rate": 3400},
    {"id": "ryu_hyung_yeol", "korean": "류형열", "english": "RYU HYUNG YEOL", "birth": 1991, "height": 188, "waist": 28, "shoes": 280, "hair": "medium", "gender": "male", "nationality": "korean", "workTypes": ["runway", "campaign", "editorial"], "looks": ["highfashion", "clean"], "rate": 8800},
    {"id": "yoon_jung_jae", "korean": "윤정재", "english": "YOON JUNG JAE", "birth": 1996, "height": 184, "waist": 28, "shoes": 280, "hair": "buzzcut", "gender": "male", "nationality": "korean", "workTypes": ["social", "ecommerce", "lookbook"], "looks": ["clean", "natural"], "rate": 900},
    {"id": "jung_hyuk", "korean": "정혁", "english": "JUNG HYUK", "birth": 1991, "height": 183, "waist": 29, "shoes": 275, "hair": "medium", "gender": "male", "nationality": "korean", "workTypes": ["commercial", "ecommerce", "event"], "looks": ["athletic", "classic"], "rate": 3500},
    {"id": "jung_yong_jin", "korean": "정용진", "english": "JUNG YONG JIN", "birth": 1990, "height": 181, "waist": 30, "shoes": 270, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["commercial", "event", "social"], "looks": ["natural", "classic"], "rate": 300},
    {"id": "kim_byung_seok", "korean": "김병석", "english": "KIM BYUNG SEOK", "birth": 1994, "height": 183, "waist": 28, "shoes": 260, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["ecommerce", "social", "lookbook"], "looks": ["clean", "natural"], "rate": 400},
    {"id": "kim_kyung_dae", "korean": "김경대", "english": "KIM KYUNG DAE", "birth": 1991, "height": 185, "waist": 28, "shoes": 265, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["editorial", "lookbook", "campaign"], "looks": ["clean", "edgy"], "rate": 2800},
    {"id": "kim_hyun_woo", "korean": "김현우", "english": "KIM HYUN WOO", "birth": 1990, "height": 185, "waist": 29, "shoes": 280, "hair": "medium", "gender": "male", "nationality": "korean", "workTypes": ["commercial", "campaign", "ecommerce"], "looks": ["athletic", "classic"], "rate": 1700},
    {"id": "kim_hyun_jung", "korean": "김현중", "english": "KIM HYUN JUNG", "birth": 1991, "height": 186, "waist": 28, "shoes": 270, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["editorial", "runway", "campaign"], "looks": ["highfashion", "edgy"], "rate": 6800},
    {"id": "byun_hee_sang", "korean": "변희상", "english": "BYUN HEE SANG", "birth": 1996, "height": 186, "waist": 28, "shoes": 270, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["social", "ecommerce", "lookbook"], "looks": ["clean", "natural"], "rate": 600},
    {"id": "lim_chae_woong", "korean": "임채웅", "english": "LIM CHAE WOONG", "birth": 1996, "height": 189, "waist": 30, "shoes": 280, "hair": "short", "gender": "male", "nationality": "korean", "workTypes": ["runway", "editorial", "campaign"], "looks": ["highfashion", "clean"], "rate": 6800},
    {"id": "jang_sung_hoon", "korean": "장성훈", "english": "JANG SUNG HOON", "birth": 1992, "height": 185, "waist": 29, "shoes": 280, "hair": "medium", "gender": "male", "nationality": "korean", "workTypes": ["commercial", "ecommerce", "lookbook"], "looks": ["classic", "natural"], "rate": 2200},
    {"id": "model_29", "korean": "", "english": "MODEL", "birth": 1990, "height": 185, "waist": 29, "shoes": 270, "hair": "medium", "gender": "male", "nationality": "other", "workTypes": ["commercial", "ecommerce"], "looks": ["clean", "natural"], "rate": 4700},
]


def get_connection():
    """Open a connection to the SQLite file. Rows come back like dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the models table if it doesn't already exist."""
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS models (
            id          TEXT PRIMARY KEY,
            korean      TEXT,
            english     TEXT,
            birth       INTEGER,
            height      INTEGER,
            waist       INTEGER,
            shoes       INTEGER,
            hair        TEXT,
            gender      TEXT,
            nationality TEXT,
            work_types  TEXT,   -- JSON list, e.g. ["runway","editorial"]
            looks       TEXT,   -- JSON list, e.g. ["clean","classic"]
            rate        INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def seed_db():
    """Fill the table with the starter models. Safe to run repeatedly."""
    conn = get_connection()
    for m in SEED_MODELS:
        conn.execute(
            """
            INSERT OR REPLACE INTO models
                (id, korean, english, birth, height, waist, shoes, hair,
                 gender, nationality, work_types, looks, rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                m["id"], m["korean"], m["english"], m["birth"], m["height"],
                m["waist"], m["shoes"], m["hair"], m["gender"], m["nationality"],
                json.dumps(m["workTypes"]), json.dumps(m["looks"]), m["rate"],
            ),
        )
    conn.commit()
    conn.close()


def _row_to_model(row):
    """Turn a database row back into the same shape the frontend expects."""
    return {
        "id": row["id"],
        "korean": row["korean"],
        "english": row["english"],
        "birth": row["birth"],
        "height": row["height"],
        "waist": row["waist"],
        "shoes": row["shoes"],
        "hair": row["hair"],
        "gender": row["gender"],
        "nationality": row["nationality"],
        "workTypes": json.loads(row["work_types"]),
        "looks": json.loads(row["looks"]),
        "rate": row["rate"],
    }


def get_all_models():
    """Return every model in the database as a list of dicts."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM models").fetchall()
    conn.close()
    return [_row_to_model(r) for r in rows]


if __name__ == "__main__":
    init_db()
    seed_db()
    count = len(get_all_models())
    print(f"Database ready at {DB_PATH} with {count} models.")
