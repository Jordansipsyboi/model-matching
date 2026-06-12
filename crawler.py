"""
Crawler for Model Matching.

How it works:
1. Reads all agencies from the database
2. For each agency not crawled in the last 24 hours, visits their website
3. Uses Playwright (real Chrome browser) to load the page and get the HTML
4. Sends the HTML to Claude API, which extracts model data like a human would
5. Saves new/updated models to the database

Run manually:
    python crawler.py

Or run for a specific agency URL:
    python crawler.py https://morphmgmt.com/women
"""

import asyncio
import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta

import anthropic
from dotenv import load_dotenv
from playwright.async_api import async_playwright

import database

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

EXTRACT_PROMPT = """You are extracting model data from a modeling agency webpage.

Look at the HTML and extract ALL models you can find. For each model return a JSON object with these fields:
- english: full name in English (string)
- korean: name in Korean if present, else empty string
- gender: "male" or "female"
- height: height in cm as integer (convert from ft/in if needed)
- chest: chest/bust in cm as integer (convert from inches if needed)
- waist: waist in cm as integer (convert from inches if needed)
- hips: hips in cm as integer (convert from inches if needed)
- shoes: shoe size in mm as integer (convert from EU/US if needed: EU*6.667 ≈ mm)
- hair_length: one of "short", "medium", "long", "buzzcut", "bald"
- hair_color: e.g. "black", "brown", "blonde"
- eye_color: e.g. "brown", "black", "blue"
- nationality: one of "korean", "japanese", "chinese", "american", "european", "southeast_asian", "other"
- workTypes: list from ["runway","editorial","campaign","commercial","ecommerce","social","lookbook","event"]
- looks: list from ["clean","edgy","athletic","highfashion","natural","classic"]
- rate: day rate in USD as integer (if not listed use 0)
- agency: the agency name (string)
- source_url: the URL this model was found on (string)

Return ONLY a JSON array of model objects. If you cannot find any models, return an empty array [].
Do not include any explanation, just the JSON."""


async def fetch_page_html(url: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            html = await page.content()
        except Exception as e:
            print(f"  Failed to load {url}: {e}")
            html = ""
        finally:
            await browser.close()
    return html


def extract_models_with_ai(html: str, agency_name: str, url: str) -> list:
    # Trim HTML to avoid token limits — keep first 80k chars
    trimmed = html[:80000] if len(html) > 80000 else html

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": f"Agency: {agency_name}\nURL: {url}\n\nHTML:\n{trimmed}\n\n{EXTRACT_PROMPT}"
            }
        ]
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  AI returned invalid JSON: {e}")
        print(f"  Raw output: {raw[:500]}")
        return []


def save_crawled_models(models: list, agency_name: str):
    conn = database.get_connection()
    added = 0
    for m in models:
        if not m.get("english"):
            continue
        model_id = m["english"].lower().replace(" ", "_").replace("'", "")
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO models
                    (id, korean, english, birth, height, chest, waist, hips, shoes,
                     hair_length, hair_color, eye_color, gender, nationality,
                     work_types, looks, rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                )
            )
            added += 1
        except Exception as e:
            print(f"  Could not save {m.get('english')}: {e}")
    conn.commit()
    conn.close()
    return added


def update_last_crawled(agency_id: int):
    conn = database.get_connection()
    conn.execute(
        "UPDATE agencies SET last_crawled_at = ? WHERE id = ?",
        (datetime.now().isoformat(), agency_id)
    )
    conn.commit()
    conn.close()


def get_agencies_to_crawl() -> list:
    conn = database.get_connection()
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    rows = conn.execute(
        """
        SELECT id, agency_name, agency_website FROM agencies
        WHERE last_crawled_at IS NULL OR last_crawled_at < ?
        """,
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def crawl_agency(agency: dict):
    name = agency["agency_name"]
    url = agency["agency_website"]
    print(f"\nCrawling: {name} ({url})")

    html = await fetch_page_html(url)
    if not html:
        print(f"  Skipping — could not load page")
        return 0

    print(f"  Page loaded ({len(html):,} chars). Sending to AI...")
    models = extract_models_with_ai(html, name, url)
    print(f"  AI found {len(models)} models")

    if models:
        added = save_crawled_models(models, name)
        print(f"  Saved {added} models to database")

    update_last_crawled(agency["id"])
    return len(models)


async def main(url_override=None):
    database.init_db()

    if url_override:
        # One-off crawl for a specific URL (for testing)
        agency = {"id": 0, "agency_name": "Test", "agency_website": url_override}
        await crawl_agency(agency)
        return

    agencies = get_agencies_to_crawl()
    if not agencies:
        print("No agencies need crawling right now.")
        return

    print(f"Found {len(agencies)} agencies to crawl.")
    total = 0
    for agency in agencies:
        total += await crawl_agency(agency)

    print(f"\nDone. Total models found: {total}")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(url))
