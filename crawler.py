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
- shoes: shoe size in mm as integer (convert from EU/US if needed: EU size * 6.667 ≈ mm)
- hair_length: one of "short", "medium", "long", "buzzcut", "bald"
- hair_color: e.g. "black", "brown", "blonde"
- eye_color: e.g. "brown", "black", "blue"
- nationality: one of "korean", "japanese", "chinese", "american", "european", "southeast_asian", "other"
- workTypes: list from ["runway","editorial","campaign","commercial","ecommerce","social","lookbook","event"]
- looks: list from ["clean","edgy","athletic","highfashion","natural","classic"]
- rate: day rate in USD as integer (if not listed use 0)
- agency: the agency name (string)
- source_url: the URL this model was found on (string)
- profile_url: the URL to this model's individual profile page if you can find it as a link in the HTML, else empty string
- photo_url: the URL of the model's main photo/headshot img src if visible, else empty string

Return ONLY a JSON array of model objects. If you cannot find any models, return an empty array [].
Do not include any explanation, just the JSON."""

PROFILE_PROMPT = """You are extracting detailed data from a single model's profile page.

Return a JSON object (not array) with these fields:
- english: full name in English
- korean: name in Korean if present, else empty string
- height: height in cm as integer (convert from ft/in if needed)
- chest: chest/bust in cm as integer
- waist: waist in cm as integer
- hips: hips in cm as integer
- shoes: shoe size in mm as integer (EU size * 6.667 ≈ mm)
- hair_length: one of "short", "medium", "long", "buzzcut", "bald"
- hair_color: e.g. "black", "brown", "blonde"
- eye_color: e.g. "brown", "black", "blue"
- photo_url: the full URL of the model's main profile photo img src (absolute URL preferred)

Return ONLY the JSON object. No explanation."""


# URL patterns that likely lead to model roster pages
ROSTER_PATTERNS = [
    "women", "men", "woman", "man", "models", "talent", "roster",
    "asian", "international", "board", "new_face", "newface",
    "female", "male", "portfolio", "ladies", "guys"
]


async def fetch_page_html(url: str) -> tuple[str, list, list]:
    """Returns (html, roster_urls, profile_urls)."""
    from urllib.parse import urljoin, urlparse
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(4000)
            html = await page.content()

            base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            current_path = urlparse(url).path.rstrip("/")
            links = await page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.getAttribute('href'))"
            )

            roster_urls = []
            profile_urls = []
            seen = set()

            for href in links:
                if not href or href.startswith("#") or href.startswith("mailto"):
                    continue
                full = urljoin(base, href).split("?")[0].split("#")[0]
                if urlparse(full).netloc != urlparse(url).netloc:
                    continue
                if full in seen:
                    continue
                seen.add(full)

                path = urlparse(full).path.rstrip("/")

                # Profile page: starts with current roster path + more path segments
                # Handles both /asian_women/kim-seojin/ and /models/men/1741247/yoon-se-chan
                if current_path and path.startswith(current_path + "/"):
                    remainder = path[len(current_path)+1:]
                    # Between 1 and 3 levels deeper (covers numeric ID + slug patterns)
                    depth = len([s for s in remainder.split("/") if s])
                    if remainder and 1 <= depth <= 3:
                        profile_urls.append(full)
                # Roster page: matches known patterns but not a profile
                elif any(p in path.lower() for p in ROSTER_PATTERNS):
                    roster_urls.append(full)

        except Exception as e:
            print(f"  Failed to load {url}: {e}")
            html = ""
            roster_urls = []
            profile_urls = []
        finally:
            await browser.close()
    return html, roster_urls, profile_urls


def call_ai(html_chunk: str, agency_name: str, url: str) -> list:
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8096,
        messages=[
            {
                "role": "user",
                "content": f"Agency: {agency_name}\nURL: {url}\n\nHTML:\n{html_chunk}\n\n{EXTRACT_PROMPT}"
            }
        ]
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def extract_models_with_ai(html: str, agency_name: str, url: str) -> list:
    # Split into 40k char chunks so output never gets cut off
    chunk_size = 40000
    chunks = [html[i:i+chunk_size] for i in range(0, min(len(html), 160000), chunk_size)]
    all_models = []
    seen_names = set()
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"    Chunk {i+1}/{len(chunks)}...")
        models = call_ai(chunk, agency_name, url)
        for m in models:
            name = m.get("english", "").strip()
            if name and name not in seen_names:
                seen_names.add(name)
                all_models.append(m)
    return all_models


def parse_profile_html(html: str, profile_url: str) -> dict:
    """Extract profile data using regex — free, no AI needed.
    Works for sites with plain-text measurements like:
    'height 176 bust 34 waist 25 hips 35 shoes 255/38.5 hair black eyes dark brown'
    Falls back to AI if regex finds nothing useful.
    """
    import re
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        result = {}

        # Name — use URL slug (most reliable across sites)
        slug = profile_url.rstrip("/").split("/")[-1]
        # Remove numeric IDs like "1741247" at the start
        parts = [p for p in slug.replace("-", " ").replace("_", " ").split() if not p.isdigit()]
        result["english"] = " ".join(parts).upper()

        # Height — English or Korean (신장)
        m = re.search(r'(?:height|신장|키)[\s:]*(\d{2,3})', text, re.I)
        if not m:
            m = re.search(r'\b(1[6-9]\d)\s*cm', text, re.I)
        if m:
            h = int(m.group(1))
            if h < 100:
                ft_in = re.search(r"(\d)'(\d+)", text)
                if ft_in:
                    h = round(int(ft_in.group(1)) * 30.48 + int(ft_in.group(2)) * 2.54)
            result["height"] = h

        # Bust/Chest — English or Korean (가슴/버스트)
        for label in [r'bust', r'chest', r'가슴', r'버스트']:
            m = re.search(rf'{label}[\s:]*(\d{{2,3}})', text, re.I)
            if m:
                v = int(m.group(1))
                result["chest"] = round(v * 2.54) if v < 60 else v  # convert inches→cm
                break

        # Waist — English or Korean (허리)
        m = re.search(r'(?:waist|허리)[\s:]*(\d{2,3})', text, re.I)
        if m:
            v = int(m.group(1))
            result["waist"] = round(v * 2.54) if v < 60 else v

        # Hips — English or Korean (엉덩이/힙)
        m = re.search(r'(?:hips?|엉덩이|힙)[\s:]*(\d{2,3})', text, re.I)
        if m:
            v = int(m.group(1))
            result["hips"] = round(v * 2.54) if v < 60 else v

        # Shoes — mm first, then EU; Korean (발/신발)
        m = re.search(r'(?:shoes?|발사이즈|발|신발)[\s:]*(\d{3})', text, re.I)
        if m:
            result["shoes"] = int(m.group(1))
        else:
            m = re.search(r'(?:shoes?|발사이즈|발|신발)[\s:]*(\d{2}(?:\.\d)?)', text, re.I)
            if m:
                eu = float(m.group(1))
                result["shoes"] = round((eu + 1.5) / 0.667 * 10)

        # Hair color
        m = re.search(r'hair[\s:]*([a-z ]+?)(?:\s+eyes|\s+$|\s{2})', text, re.I)
        if m:
            result["hair_color"] = m.group(1).strip().lower()
            result["hair_length"] = "medium"

        # Eye color — only capture 1-2 words, stop before "compcard" or other junk
        m = re.search(r'eyes?[\s:]*([a-z]+(?:\s+[a-z]+)?)', text, re.I)
        if m:
            eye = m.group(1).strip().lower()
            # Reject if it captured non-color words
            if not any(bad in eye for bad in ["compcard", "comp", "card", "listed", "profile"]):
                result["eye_color"] = eye

        # Gender — infer from roster URL path (check women before men to avoid "women" matching "men")
        path = profile_url.lower()
        if any(w in path for w in ["women", "female", "ladies", "asian_women", "international_women"]):
            result["gender"] = "female"
        elif any(w in path for w in ["asian_men", "international_men", "/men/", "male", "guys"]):
            result["gender"] = "male"

        # Photo — try og:image first, then wp-content images, then any large img
        from urllib.parse import urlparse
        parsed_url = urlparse(profile_url)
        base_origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

        og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
        if og and og.get("content"):
            result["photo_url"] = og["content"]
        else:
            # Find all imgs, prefer ones with wp-content or large paths (skip logos/icons)
            for img in soup.find_all("img", src=True):
                src = img["src"]
                if any(skip in src.lower() for skip in ["logo", "icon", "favicon", "sprite", "placeholder"]):
                    continue
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = base_origin + src
                if src.startswith("http"):
                    result["photo_url"] = src
                    break

        return result

    except Exception:
        return {}


def fetch_profile_details(html: str, profile_url: str) -> dict:
    trimmed = html[:40000]
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": f"URL: {profile_url}\n\nHTML:\n{trimmed}\n\n{PROFILE_PROMPT}"}]
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


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
                     work_types, looks, rate, photo_url, agency_name, profile_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                )
            )
            added += 1
        except Exception as e:
            print(f"  Could not save {m.get('english')}: {e}")
    conn.commit()
    conn.close()
    return added


async def crawl_profiles_directly(profile_urls: list, agency_name: str, existing_models: list) -> list:
    """Crawl individual profile pages and build/enrich model list from them."""
    from urllib.parse import urljoin, urlparse

    # Build lookup by name for merging with roster data
    by_name = {m["english"].upper(): m for m in existing_models if m.get("english")}

    results = []
    for i, profile_url in enumerate(profile_urls):
        print(f"  Profile {i+1}/{len(profile_urls)}: {profile_url.rstrip('/').split('/')[-1]}")
        try:
            html, _, _ = await fetch_page_html(profile_url)
            if not html:
                continue
            # Try regex first (free), fall back to AI only if needed
            details = parse_profile_html(html, profile_url)
            print(f"    Regex got: height={details.get('height')} chest={details.get('chest')} waist={details.get('waist')}")
            if not details or not details.get("height"):
                print(f"    Using AI fallback...")
                details = fetch_profile_details(html, profile_url)
            if not details or not details.get("english"):
                continue

            # Merge with any existing roster data for this model
            name_key = details["english"].upper()
            base = by_name.get(name_key, {})

            model = {
                "english": details.get("english", base.get("english", "")),
                "korean": details.get("korean") or base.get("korean", ""),
                "gender": details.get("gender") or base.get("gender", "female"),
                "nationality": base.get("nationality", "other"),
                "workTypes": base.get("workTypes", []),
                "looks": base.get("looks", []),
                "birth": base.get("birth", 1995),
                "rate": 0,
                "height": details.get("height") or base.get("height", 0),
                "chest": details.get("chest") or base.get("chest", 0),
                "waist": details.get("waist") or base.get("waist", 0),
                "hips": details.get("hips") or base.get("hips", 0),
                "shoes": details.get("shoes") or base.get("shoes", 0),
                "hair_length": details.get("hair_length") or base.get("hair_length", "medium"),
                "hair_color": details.get("hair_color") or base.get("hair_color", "black"),
                "eye_color": details.get("eye_color") or base.get("eye_color", "brown"),
                "photo_url": details.get("photo_url", ""),
                "profile_url": profile_url,
                "agency": agency_name,
            }
            results.append(model)
        except Exception as e:
            print(f"    Error: {e}")

    # Add any roster models that didn't have a profile page
    result_names = {m["english"].upper() for m in results}
    for m in existing_models:
        if m.get("english", "").upper() not in result_names:
            results.append(m)

    return results


async def enrich_model_profiles(models: list, base_url: str, agency_name: str):
    """Visit each model's individual profile page to get photo + measurements."""
    from urllib.parse import urljoin, urlparse
    base = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"

    enriched = 0
    for m in models:
        profile_url = m.get("profile_url", "")
        if not profile_url:
            continue
        # Make absolute URL
        if profile_url.startswith("/"):
            profile_url = urljoin(base, profile_url)
        if not profile_url.startswith("http"):
            continue

        try:
            html, _ = await fetch_page_html(profile_url)
            if not html:
                continue
            details = fetch_profile_details(html, profile_url)
            if details:
                # Merge details into model, only overwrite zeros
                for field in ["height", "chest", "waist", "hips", "shoes"]:
                    if details.get(field) and m.get(field, 0) == 0:
                        m[field] = details[field]
                for field in ["hair_length", "hair_color", "eye_color", "photo_url"]:
                    if details.get(field) and not m.get(field):
                        m[field] = details[field]
                if details.get("photo_url"):
                    m["photo_url"] = details["photo_url"]
                enriched += 1
        except Exception as e:
            print(f"  Profile fetch error for {m.get('english')}: {e}")

    print(f"  Enriched {enriched}/{len(models)} profiles with photo + measurements")
    return models


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

    html, roster_urls, profile_urls = await fetch_page_html(url)
    if not html:
        print(f"  Skipping — could not load page")
        return 0

    # Try the homepage first
    print(f"  Page loaded ({len(html):,} chars). Sending to AI...")
    models = extract_models_with_ai(html, name, url)
    print(f"  AI found {len(models)} models on homepage")

    all_profile_urls = list(profile_urls)

    # If homepage had no models, try roster sub-pages
    if not models and roster_urls:
        print(f"  Found {len(roster_urls)} roster sub-pages: {roster_urls[:5]}")
        for roster_url in roster_urls[:6]:
            print(f"  Trying: {roster_url}")
            sub_html, _, sub_profiles = await fetch_page_html(roster_url)
            if not sub_html:
                continue
            sub_models = extract_models_with_ai(sub_html, name, roster_url)
            print(f"  AI found {len(sub_models)} models, {len(sub_profiles)} profile links on {roster_url.split('/')[-2]}/")
            models.extend(sub_models)
            all_profile_urls.extend(sub_profiles)

    if models or all_profile_urls:
        # If we have direct profile URLs, crawl them for full details
        if all_profile_urls:
            print(f"  Found {len(all_profile_urls)} profile pages — crawling for photos + measurements...")
            models = await crawl_profiles_directly(all_profile_urls, name, models)
        added = save_crawled_models(models, name)
        print(f"  Saved {added} models to database")
    else:
        print(f"  No models found on any page")

    update_last_crawled(agency["id"])
    return len(models)


async def main(url_override=None):
    database.init_db()

    if url_override:
        from urllib.parse import urlparse
        host = urlparse(url_override).netloc.replace("www.", "")
        name_map = {
            "jmodelmanagement.co.kr": "J Model Management",
            "morphmgmt.com": "MORPH Management",
            "models.com": "Models.com",
        }
        agency_name = name_map.get(host, host)
        agency = {"id": 0, "agency_name": agency_name, "agency_website": url_override}
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
