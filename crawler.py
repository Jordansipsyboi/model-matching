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

PROFILE_PROMPT = """You are extracting detailed data from a single model's profile page. Below is the page's VISIBLE TEXT (HTML tags already stripped out).

Return a JSON object (not array) with these fields:
- english: full name in English
- korean: name in Korean if present, else empty string
- gender: "male" or "female" — infer from any pronouns, section labels (men/women), the model's name, or the photo description. Empty string only if truly impossible to tell.
- height: height in cm as integer (convert from ft/in if needed, e.g. 5'9" -> 175)
- chest: chest/bust in cm as integer (convert from inches if the site lists it in inches, inches * 2.54 = cm)
- waist: waist in cm as integer (convert from inches if needed)
- hips: hips in cm as integer (convert from inches if needed)
- shoes: shoe size in mm as integer (convert from EU/US/UK if needed: EU size * 6.667 ≈ mm)
- hair_length: one of "short", "medium", "long", "buzzcut", "bald"
- hair_color: e.g. "black", "brown", "blonde"
- eye_color: e.g. "brown", "black", "blue"

IMPORTANT — dual cm/imperial format: many sites print each measurement as
"<cm>/<imperial>", e.g. "HEIGHT 185/6'1\"", "CHEST 99/39\"", "WAIST 80/31.5\"".
In every "X/Y" pair the FIRST number (before the slash) is ALREADY in centimeters
— just use it directly (chest here is 99, waist is 80). Do NOT try to convert the
second number; it's the same measurement in feet/inches. "SHOE 285MM" means shoes=285.

Other formats: compact like "176 / 34 / 25 / 35" (height/bust/waist/hips), or
Korean labels (신장=height, 가슴=chest, 허리=waist, 힙=hips, 발사이즈=shoe size).
Only convert units when a value is given solely in inches/feet/EU with no cm.

Return ONLY the JSON object. No explanation."""


# Same task, but reading the numbers off a compcard IMAGE instead of page text.
# Many agencies print measurements directly on the model's photo/compcard, so
# there is no text to scrape — only the image has the data.
VISION_PROMPT = """This is a modeling compcard/profile image. Read any measurements printed on it.

Return a JSON object with these fields (use 0 / empty string if not visible on the image):
- height: height in cm as integer (convert from ft/in if needed, e.g. 5'9" -> 175)
- chest: chest/bust in cm as integer (inches * 2.54 = cm)
- waist: waist in cm as integer (convert from inches if needed)
- hips: hips in cm as integer (convert from inches if needed)
- shoes: shoe size in mm as integer (EU size * 6.667 ≈ mm)
- hair_color: e.g. "black", "brown", "blonde" — best guess from the photo if not labeled
- eye_color: e.g. "brown", "black", "blue" — best guess if not labeled

Measurements are often compact like "176 / 84 / 60 / 88" (height/bust/waist/hips) or labeled in Korean (신장=height, 가슴=chest, 허리=waist, 힙=hips, 발=shoe). Convert units as needed.

Return ONLY the JSON object. No explanation."""


def extract_measurements_from_image(photo_url: str) -> dict:
    """Vision fallback: download the compcard image and let Claude read the
    measurements printed on it. Used when the page text has no usable numbers
    (common — many agencies bake measurements into the photo, not the HTML)."""
    if not photo_url:
        return {}
    try:
        import urllib.request
        import base64

        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(photo_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            img_bytes = resp.read()
            ctype = resp.headers.get("Content-Type", "image/jpeg")

        media_type = "image/jpeg"
        for t in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            if t.split("/")[1] in ctype.lower():
                media_type = t
                break

        b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": VISION_PROMPT},
            ]}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        print(f"    Vision fallback failed: {e}")
        return {}


# URL patterns that likely lead to model roster pages
ROSTER_PATTERNS = [
    "women", "men", "woman", "man", "models", "talent", "roster",
    "asian", "international", "board", "new_face", "newface",
    "female", "male", "portfolio", "ladies", "guys"
]


async def fetch_page_html(url: str, scroll: bool = True, settle_ms: int = 4000,
                          profile: bool = False) -> tuple[str, list, list]:
    """Returns (html, roster_urls, profile_urls). Pass scroll=False for single
    profile pages — the scroll-to-load-more behavior is only needed for long
    roster/listing pages, and skipping it makes profile crawls much faster.
    settle_ms is how long to pause after DOM load for JS to render; bump it on
    slow JS sites that haven't painted their content yet on the first try.
    profile=True turns on the profile-render step: many agency sites are SPAs
    that inject the measurement block via JS only after the photo loads / after a
    stats toggle is opened. We scroll, click any stats/portfolio toggle, and wait
    for measurement text (HEIGHT/CHEST/cm/신장) to actually appear before reading."""
    from urllib.parse import urljoin, urlparse
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR",
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                # A same-origin Referer makes deep links (e.g. view.php?idx=) look
                # like a real click-through from the site's own listing, which some
                # agency sites require before serving the full profile content.
                "Referer": origin + "/",
            },
        )
        # Hide the automation flag — some sites withhold content when
        # navigator.webdriver is true.
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()
        try:
            # Establish a session first. Some sites (e.g. evermodel) redirect a
            # deep link like view.php?idx=862 straight to a default page unless the
            # request carries a session cookie that a real visitor picks up by
            # landing on the site first. Visiting the origin in this same context
            # seeds that cookie, so the subsequent profile navigation isn't bounced.
            if profile:
                try:
                    await page.goto(origin + "/", wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(800)
                except Exception:
                    pass

            # "domcontentloaded" instead of "networkidle": many sites keep
            # background connections (analytics, chat widgets, video) open
            # forever, so networkidle never settles and times out. We wait for
            # the DOM, then a fixed pause to let content render.
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                await page.goto(url, wait_until="commit", timeout=60000)
            await page.wait_for_timeout(settle_ms)
            # Give JS-heavy sites (Wix, React, etc) extra time to render their
            # content grid. networkidle often never settles, so cap it short and
            # ignore the timeout — it's a best-effort extra wait, not required.
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            if scroll:
                # Scroll repeatedly to trigger lazy-loaded / infinite-scroll roster lists
                # so large rosters (50-100+ models) aren't cut off after the first screen.
                last_height = 0
                for _ in range(10):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1200)
                    height = await page.evaluate("document.body.scrollHeight")
                    if height == last_height:
                        break
                    last_height = height
                await page.wait_for_timeout(1500)

            if profile:
                # SPA profile pages inject the stat block (HEIGHT/CHEST/...) via JS
                # after the photo, often hidden behind a "Portfolio"/"Stats" toggle.
                # 1) scroll the whole page so anything lazy-rendered gets triggered.
                for _ in range(6):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(800)
                # 2) click any element whose label suggests it reveals the stats.
                for label in ["PORTFOLIO", "Portfolio", "STATS", "Stats",
                              "DETAILS", "Details", "MEASUREMENTS", "Measurements",
                              "INFO", "Info", "PROFILE", "Profile"]:
                    try:
                        el = page.get_by_text(label, exact=False).first
                        if await el.count() > 0:
                            await el.click(timeout=1500)
                            await page.wait_for_timeout(600)
                    except Exception:
                        pass
                # 3) wait (best-effort) for the measurement text to actually appear.
                try:
                    await page.wait_for_function(
                        "/HEIGHT|CHEST|WAIST|신장|가슴|\\b\\d{3}\\s*cm/i.test(document.body.innerText)",
                        timeout=15000,
                    )
                except Exception:
                    pass
                await page.wait_for_timeout(800)

            # Grab the LIVE rendered text from the DOM (not the static serialized
            # HTML from page.content()). innerText reflects the actual flattened
            # render tree, including content injected into Shadow DOM web
            # components — which page.content()/BeautifulSoup silently drop, since
            # shadow roots are never included in HTML serialization. Some sites
            # (e.g. morphmgmt's stat widget) render real, visible measurement text
            # this way — invisible to a plain HTML scrape, visible to a human.
            # DEBUG: capture the final URL (reveals redirects) and a screenshot of
            # exactly what the headless browser actually rendered — ground truth for
            # "site renders for me but not the scraper" problems.
            if os.environ.get("CRAWL_DEBUG"):
                try:
                    print(f"    [debug] requested={url}")
                    print(f"    [debug] landed on={page.url}")
                    os.makedirs("debug_screens", exist_ok=True)
                    slug = url.rstrip("/").split("/")[-1] or "page"
                    await page.screenshot(path=f"debug_screens/{slug}.png", full_page=True)
                    print(f"    [debug] screenshot -> debug_screens/{slug}.png")
                except Exception as e:
                    print(f"    [debug] screenshot failed: {e}")

            rendered_text = ""
            try:
                rendered_text = await page.evaluate("document.body.innerText")
            except Exception:
                pass

            # Some sites (e.g. evermodel) render the whole profile card — name,
            # measurements, photo — inside an <iframe>, which is a separate document
            # that page.body.innerText never reaches. Pull each child frame's text
            # too and append it so those measurements aren't lost.
            try:
                for fr in page.frames:
                    if fr is page.main_frame:
                        continue
                    try:
                        ftext = await fr.evaluate("document.body ? document.body.innerText : ''")
                    except Exception:
                        ftext = ""
                    if ftext and ftext.strip():
                        rendered_text = (rendered_text + "\n" + ftext) if rendered_text else ftext
            except Exception:
                pass

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
                # Keep the query string: on .php sites the profile id lives there
                # (view.php?idx=5), so stripping it would collapse every profile
                # into one URL. Only drop the #fragment.
                full = urljoin(base, href).split("#")[0]
                if urlparse(full).netloc != urlparse(url).netloc:
                    continue
                if full in seen:
                    continue
                seen.add(full)

                path = urlparse(full).path.rstrip("/")
                segments = [s for s in path.split("/") if s]

                # Dedicated profile-container paths like /model/ahlam-amani/,
                # /models/jane-doe/, /talent/john-smith/, /portfolio/xyz/ — a known
                # singular container segment followed by exactly one slug. These live
                # OUTSIDE the roster path so the prefix check below would miss them.
                # But guard against category sections like /models/women, /models/men
                # which look the same shape but are rosters, not people.
                PROFILE_CONTAINERS = {"model", "models", "talent", "talents", "portfolio", "profile"}
                CATEGORY_WORDS = {
                    "women", "men", "woman", "man", "female", "male", "ladies", "guys",
                    "new", "new-faces", "newfaces", "new_faces", "main", "board",
                    "development", "international", "asian", "europe", "influencer",
                    "influencers", "management", "kids", "junior", "senior", "all",
                    # Marketing / category / non-person links that look like profile
                    # slugs but aren't actual models — skip so we don't waste crawls.
                    "dancer", "dancers", "singer", "singers", "actor", "actors",
                    "actress", "musician", "artist", "artists", "creator", "creators",
                    "model", "talent", "talents", "booking", "direct-booking",
                    "beauty", "eurasian-beauty", "contact", "about", "news", "press",
                    "blog", "faq", "terms", "privacy", "category", "categories",
                    "search", "login", "signup", "cart", "home", "gallery", "portfolio",
                    # Listing/index endpoints (common on .php sites) — these are
                    # rosters, not people, even though they sit under /models/.
                    "list", "list.php", "index", "index.php", "lists.php",
                }
                # A profile container ("portfolio"/"model"/"talent"/...) immediately
                # followed by a single slug is a person page, wherever the container
                # sits in the path: /model/jane, /portfolio/jane, AND /w/portfolio/jane
                # (wagency-style, where the container is NOT the first segment). The
                # final slug must not be a category/marketing word.
                if (len(segments) >= 2 and segments[-2].lower() in PROFILE_CONTAINERS
                        and segments[-1].lower() not in CATEGORY_WORDS):
                    profile_urls.append(full)
                # Profile page: starts with current roster path + more path segments
                # Handles both /asian_women/kim-seojin/ and /models/men/1741247/yoon-se-chan
                elif current_path and path.startswith(current_path + "/"):
                    remainder = path[len(current_path)+1:]
                    # Between 1 and 3 levels deeper (covers numeric ID + slug patterns)
                    depth = len([s for s in remainder.split("/") if s])
                    # Skip non-person links (e.g. /models/women/dancer) — the final
                    # slug being a category/marketing word means it's not a real model.
                    if remainder and 1 <= depth <= 3 and segments[-1].lower() not in CATEGORY_WORDS:
                        profile_urls.append(full)
                # Roster page: matches known patterns but not a profile
                elif any(p in path.lower() for p in ROSTER_PATTERNS):
                    roster_urls.append(full)

        except Exception as e:
            print(f"  Failed to load {url}: {e}")
            html = ""
            rendered_text = ""
            roster_urls = []
            profile_urls = []
        finally:
            await browser.close()

    profile_urls = _dedupe_profile_urls(profile_urls)
    return html, roster_urls, profile_urls, rendered_text


def _dedupe_profile_urls(profile_urls: list) -> list:
    """Some sites expose the same model under two URL shapes — an id-less one
    like /models/women/jane-doe (which actually serves the ROSTER listing, not a
    profile) and the real one /models/women/123456/jane-doe (numeric id segment).
    When a slug appears in both shapes, keep only the id-bearing URL; otherwise
    we'd crawl the listing page and get zero measurements."""
    import re as _re
    from urllib.parse import urlparse

    def final_slug(u):
        parsed = urlparse(u)
        segs = [s for s in parsed.path.split("/") if s]
        base = segs[-1].lower() if segs else u
        # On query-param sites the same path (view.php) serves every profile and
        # only the query (?idx=5) tells them apart — fold it into the key so they
        # don't all dedupe down to one.
        return f"{base}?{parsed.query}" if parsed.query else base

    def has_numeric_segment(u):
        segs = [s for s in urlparse(u).path.split("/") if s]
        return any(_re.fullmatch(r"\d+", s) for s in segs)

    by_slug = {}
    for u in profile_urls:
        by_slug.setdefault(final_slug(u), []).append(u)

    result = []
    for slug, urls in by_slug.items():
        id_forms = [u for u in urls if has_numeric_segment(u)]
        # If any id-bearing form exists for this slug, those are the real
        # profiles — drop the id-less duplicates. Otherwise keep what we have.
        result.extend(id_forms if id_forms else urls)
    return result


def _profile_urls_from_models(models: list, page_url: str) -> list:
    """Profile-page links the AI read directly off each model's card in the HTML.
    This is scheme-agnostic — it works whether a site links profiles as
    /portfolio/sofia-s-2 or view.php?idx=5 — so it succeeds where the URL-path
    guessing fails. Relative hrefs are resolved against the page they were found
    on, and query strings are kept intact (they're the profile id on .php sites)."""
    from urllib.parse import urljoin, urlparse

    page_host = urlparse(page_url).netloc
    out = []
    for m in models:
        href = (m.get("profile_url") or "").strip()
        if not href or href.startswith(("#", "mailto", "javascript", "tel")):
            continue
        full = urljoin(page_url, href).split("#")[0]
        if urlparse(full).netloc != page_host:
            continue
        out.append(full)
    return out


async def crawl_roster_section(url: str, agency_name: str, max_pages: int = 12) -> tuple[list, list]:
    """Crawl a roster URL (e.g. a "Women" or "Men" section) and any of its
    numbered pagination continuations, merging models + profile links until
    a page adds nothing new. Handles rosters split across multiple pages
    (?page=2, /page/2/, etc.) so large sections (50-100+ models) aren't
    cut off after the first page."""
    import re as _re

    all_models = []
    all_profiles = []
    seen_names = set()
    seen_profiles = set()
    current_url = url

    for page_num in range(1, max_pages + 1):
        html, _, profile_urls, _ = await fetch_page_html(current_url)
        if not html:
            break

        models = extract_models_with_ai(html, agency_name, current_url)
        # Merge AI-read profile links (handles ?query-based sites) with heuristic ones.
        profile_urls = list(dict.fromkeys(profile_urls + _profile_urls_from_models(models, current_url)))
        new_models = [m for m in models if m.get("english", "").strip().upper() not in seen_names]
        new_profiles = [p for p in profile_urls if p not in seen_profiles]

        if not new_models and not new_profiles and page_num > 1:
            break

        for m in new_models:
            seen_names.add(m["english"].strip().upper())
        seen_profiles.update(new_profiles)
        all_models.extend(new_models)
        all_profiles.extend(new_profiles)
        print(f"    Page {page_num}: {len(new_models)} new model(s), {len(new_profiles)} new profile link(s)")

        if not new_models and not new_profiles:
            break

        # Only keep guessing further pages if this page actually shows evidence
        # of pagination (a real "page=2"/"/page/2" link or next-page control) —
        # otherwise blindly trying ?page=2, ?page=3... on a single-page roster
        # just burns AI calls re-parsing the same content for nothing.
        has_pagination = bool(_re.search(r'page=\d|/page/\d|rel=["\']next["\']|class=["\'][^"\']*pag(?:e|ination)', html, _re.I))
        if not has_pagination:
            break

        # Guess the next page URL
        if _re.search(r'([?&]page=)(\d+)', current_url):
            next_url = _re.sub(r'([?&]page=)\d+', rf'\g<1>{page_num + 1}', current_url)
        elif "?" in url:
            next_url = f"{url}&page={page_num + 1}"
        else:
            next_url = f"{url}&page={page_num + 1}" if "?" in url else f"{url}?page={page_num + 1}"

        if next_url == current_url:
            break
        current_url = next_url

    return all_models, all_profiles


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


def extract_photo_url(html: str, profile_url: str) -> str:
    """Deterministically find the model's main photo — no AI needed for this part."""
    from urllib.parse import urlparse
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "html.parser")
        parsed = urlparse(profile_url)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"

        og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
        if og and og.get("content"):
            src = og["content"]
            if src.startswith("//"):
                return "https:" + src
            if src.startswith("/"):
                return base_origin + src
            return src

        for img in soup.find_all("img", src=True):
            src = img["src"]
            if any(skip in src.lower() for skip in ["logo", "icon", "favicon", "sprite", "placeholder"]):
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = base_origin + src
            if src.startswith("http"):
                return src
    except Exception:
        pass
    return ""


def fetch_profile_details(html: str, profile_url: str, rendered_text: str = "") -> dict:
    from bs4 import BeautifulSoup

    photo_url = extract_photo_url(html, profile_url)

    # Prefer the LIVE rendered text (captured via page.evaluate("innerText"))
    # over re-parsing the static HTML. Some sites inject content (e.g. stat
    # widgets) into Shadow DOM, which page.content()/BeautifulSoup can never
    # see since shadow roots aren't included in HTML serialization — but the
    # rendered text is, since it reflects what's actually drawn on screen.
    if rendered_text and rendered_text.strip():
        text = rendered_text.strip()[:20000]
    else:
        # Fallback: strip the static HTML to visible text only (nav/scripts/
        # styles stripped) — full HTML easily blows past the 40k char window
        # before reaching the actual measurements further down the page.
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)[:20000]

    # DEBUG: dump exactly what text the crawler sees for this profile, so we can
    # tell whether measurements are even present in the rendered page or not.
    if os.environ.get("CRAWL_DEBUG"):
        try:
            os.makedirs("debug_profiles", exist_ok=True)
            slug = profile_url.rstrip("/").split("/")[-1] or "page"
            with open(f"debug_profiles/{slug}.txt", "w") as f:
                f.write(text)
            # Also dump the raw HTML so we can tell whether the measurements are
            # in the DOM at all (just hidden from innerText) vs not present yet.
            with open(f"debug_profiles/{slug}.html", "w") as f:
                f.write(html or "")
        except Exception:
            pass

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": f"URL: {profile_url}\n\nPAGE TEXT:\n{text}\n\n{PROFILE_PROMPT}"}]
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        details = json.loads(raw)
    except json.JSONDecodeError:
        details = {}

    # If the page text gave us no usable measurements, the numbers are almost
    # certainly printed on the compcard image instead. Fall back to reading them
    # off the photo with Claude vision, and fill in only the missing fields.
    measure_fields = ("height", "chest", "waist", "hips")
    if photo_url and not any(details.get(f) for f in measure_fields):
        print("    No measurements in text — trying compcard image (vision)...")
        vision = extract_measurements_from_image(photo_url)
        if vision:
            for f in ("height", "chest", "waist", "hips", "shoes", "hair_color", "eye_color"):
                if not details.get(f) and vision.get(f):
                    details[f] = vision[f]

    if photo_url:
        details["photo_url"] = photo_url
    return details


PHOTO_DIR = os.path.join(os.path.dirname(__file__), "static", "model_photos")


def download_photo(photo_url: str, model_id: str) -> str:
    """Download a photo from an external URL, save it locally, and return the
    local /static/... path. Returns the original URL unchanged on any failure.
    Skips download if a local file already exists for this model_id."""
    import urllib.request
    import urllib.error

    if not photo_url or photo_url.startswith("/static/"):
        return photo_url  # already local

    os.makedirs(PHOTO_DIR, exist_ok=True)

    # Try common image extensions; fall back to .jpg
    ext = ".jpg"
    for candidate in (".jpg", ".jpeg", ".png", ".webp"):
        if photo_url.lower().split("?")[0].endswith(candidate):
            ext = candidate
            break

    filename = f"{model_id}{ext}"
    local_path = os.path.join(PHOTO_DIR, filename)

    if os.path.exists(local_path):
        return f"/static/model_photos/{filename}"

    from urllib.parse import quote, urlsplit, urlunsplit
    import time
    parts = urlsplit(photo_url)
    safe_url = urlunsplit(parts._replace(path=quote(parts.path, safe="/:@!$&'()*+,;=")))
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "/".join(photo_url.split("/")[:3]) + "/",
    }
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(safe_url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            with open(local_path, "wb") as f:
                f.write(data)
            return f"/static/model_photos/{filename}"
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)  # 1s, 2s
    print(f"    [photo] could not download {photo_url}: {last_err}")
    return photo_url


def extract_embedding_from_url(photo_url: str):
    """Extract face embedding from a photo — either a local /static/... path or
    an external URL. Returns bytes or None."""
    try:
        import urllib.request
        import tempfile
        import numpy as np
        from face1n import AuraFaceComparator

        if not photo_url:
            return None

        comparator = _get_face_comparator()
        if comparator is None:
            return None

        # Local file — resolve to filesystem path and read directly.
        if photo_url.startswith("/static/"):
            local_path = os.path.join(os.path.dirname(__file__), photo_url.lstrip("/"))
            if not os.path.exists(local_path):
                return None
            with open(local_path, "rb") as f:
                img_data = f.read()
        else:
            from urllib.parse import quote, urlsplit, urlunsplit
            parts = urlsplit(photo_url)
            safe_url = urlunsplit(parts._replace(path=quote(parts.path, safe="/:@!$&'()*+,;=")))
            headers = {"User-Agent": "Mozilla/5.0"}
            req = urllib.request.Request(safe_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                img_data = resp.read()

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(img_data)
            tmp_path = tmp.name

        try:
            embedding, _ = comparator.extract_face_embedding_optimized(tmp_path)
        finally:
            os.unlink(tmp_path)

        if embedding is None:
            return None

        embedding = embedding.astype("float32")
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.tobytes()
    except Exception as e:
        print(f"    Face embedding extraction failed: {e}")
        return None


_face_comparator = None

def _get_face_comparator():
    global _face_comparator
    if _face_comparator is None:
        try:
            from face1n import AuraFaceComparator
            _face_comparator = AuraFaceComparator()
        except Exception as e:
            print(f"  [FaceSDK] Could not load AuraFaceComparator: {e}")
    return _face_comparator


def save_crawled_models(models: list, agency_name: str):
    conn = database.get_connection()
    added = 0
    for m in models:
        if not m.get("english"):
            continue
        import re as _re
        model_id = _re.sub(r'[^a-z0-9]+', '_', m["english"].lower()).strip('_')

        # Download photo locally so it's always available (no external URL dependency)
        # then extract the face embedding from the local file.
        face_embedding = None
        if m.get("photo_url"):
            local_url = download_photo(m["photo_url"], model_id)
            m["photo_url"] = local_url
            print(f"    Extracting face embedding for {m['english']}...")
            face_embedding = extract_embedding_from_url(local_url)
            if face_embedding:
                print(f"    ✓ Face embedding saved ({len(face_embedding)} bytes)")

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO models
                        (id, korean, english, birth, height, chest, waist, hips, shoes,
                         hair_length, hair_color, eye_color, gender, nationality,
                         work_types, looks, rate, photo_url, agency_name, profile_url,
                         face_embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        korean=VALUES(korean), english=VALUES(english), birth=VALUES(birth),
                        height=VALUES(height), chest=VALUES(chest), waist=VALUES(waist),
                        hips=VALUES(hips), shoes=VALUES(shoes), hair_length=VALUES(hair_length),
                        hair_color=VALUES(hair_color), eye_color=VALUES(eye_color),
                        gender=VALUES(gender), nationality=VALUES(nationality),
                        work_types=VALUES(work_types), looks=VALUES(looks), rate=VALUES(rate),
                        photo_url=VALUES(photo_url), agency_name=VALUES(agency_name),
                        profile_url=VALUES(profile_url),
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
                    )
                )
            added += 1
        except Exception as e:
            print(f"  Could not save {m.get('english')}: {e}")
    conn.commit()
    conn.close()
    return added


async def crawl_profiles_directly(profile_urls: list, agency_name: str, existing_models: list, force: bool = False) -> list:
    """Crawl individual profile pages and build/enrich model list from them.

    On re-crawls, profiles we've already extracted before (matched by profile_url)
    are reused as-is instead of being re-fetched/re-parsed/re-AI'd, so repeat crawls
    only spend money on people who are new since the last crawl.
    """
    from urllib.parse import urljoin, urlparse

    # Build lookup by name for merging with roster data
    by_name = {m["english"].upper(): m for m in existing_models if m.get("english")}

    # People we've already crawled for this agency before (skip them unless forced)
    known_by_url = {} if force else database.get_existing_profile_urls(agency_name)

    results = []
    for i, profile_url in enumerate(profile_urls):
        if profile_url in known_by_url:
            print(f"  Profile {i+1}/{len(profile_urls)}: already known, skipping re-crawl ({profile_url.rstrip('/').split('/')[-1]})")
            results.append(known_by_url[profile_url])
            continue
        print(f"  Profile {i+1}/{len(profile_urls)}: {profile_url.rstrip('/').split('/')[-1]}")
        try:
            BOUNDS = {"height": (120, 220), "chest": (60, 130), "waist": (45, 120),
                      "hips": (60, 140), "shoes": (180, 340)}

            def _extract(html, rendered_text=""):
                d = fetch_profile_details(html, profile_url, rendered_text)
                # Reject impossible measurements (e.g. AI misreading a roster page
                # as one person and returning chest=218). Out-of-range -> missing.
                for f, (lo, hi) in BOUNDS.items():
                    v = d.get(f)
                    if v and not (lo <= v <= hi):
                        d[f] = 0
                return d

            html, _, _, rendered_text = await fetch_page_html(profile_url, scroll=False, profile=True)
            if not html:
                continue
            details = _extract(html, rendered_text)
            # If the profile-render step still didn't surface measurements, retry
            # once with a longer settle in case the SPA was just slow this time.
            if not any(details.get(f) for f in ("height", "chest", "waist", "hips")):
                print("    Empty on first read — retrying with longer wait...")
                html, _, _, rendered_text = await fetch_page_html(profile_url, scroll=True, settle_ms=10000, profile=True)
                if html:
                    retry = _extract(html, rendered_text)
                    if any(retry.get(f) for f in ("height", "chest", "waist", "hips")):
                        details = retry
            print(f"    AI got: height={details.get('height')} chest={details.get('chest')} waist={details.get('waist')}")
            if not details or not details.get("english"):
                continue

            # Merge with any existing roster data for this model
            name_key = details["english"].upper()
            base = by_name.get(name_key, {})

            # Infer gender from the URL path (e.g. /international_men/, /women/) —
            # most reliable signal, since profile pages rarely state gender and the
            # roster name-match can miss, which used to default everyone to female.
            path_l = profile_url.lower()
            url_gender = None
            if any(w in path_l for w in ["women", "female", "ladies", "_woman", "/woman"]):
                url_gender = "female"
            elif any(w in path_l for w in ["_men", "/men", "male", "guys", "_man", "/man"]):
                url_gender = "male"

            model = {
                "english": details.get("english", base.get("english", "")),
                "korean": details.get("korean") or base.get("korean", ""),
                "gender": url_gender or details.get("gender") or base.get("gender", "female"),
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
            if not any(model.get(f) for f in ("height", "chest", "waist", "hips")):
                print(f"    Skipping {model['english']} — AI found no measurements on this page")
                continue
            # Save immediately so Ctrl+C never loses progress
            save_crawled_models([model], agency_name)
            results.append(model)
        except Exception as e:
            print(f"    Error: {e}")

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
            html, _, _, rendered_text = await fetch_page_html(profile_url, profile=True)
            if not html:
                continue
            details = fetch_profile_details(html, profile_url, rendered_text)
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
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE agencies SET last_crawled_at = %s WHERE id = %s",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), agency_id)
        )
    conn.commit()
    conn.close()


def get_agencies_to_crawl() -> list:
    conn = database.get_connection()
    cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, agency_name, agency_website FROM agencies
            WHERE last_crawled_at IS NULL OR last_crawled_at < %s
            """,
            (cutoff,)
        )
        rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def crawl_agency(agency: dict, force: bool = False):
    name = agency["agency_name"]
    url = agency["agency_website"]
    print(f"\nCrawling: {name} ({url})")

    html, roster_urls, profile_urls, _ = await fetch_page_html(url)
    if not html:
        print(f"  Skipping — could not load page")
        return 0

    # Try the homepage first
    print(f"  Page loaded ({len(html):,} chars). Sending to AI...")
    models = extract_models_with_ai(html, name, url)
    print(f"  AI found {len(models)} models on homepage")

    # Prefer the profile links the AI read straight off the page (scheme-agnostic)
    # and merge them with whatever the URL-path heuristic found, deduped.
    profile_urls = list(dict.fromkeys(profile_urls + _profile_urls_from_models(models, url)))

    seen_names = {m.get("english", "").strip().upper() for m in models if m.get("english")}
    seen_profiles = set(profile_urls)
    all_profile_urls = list(profile_urls)
    total_saved = 0

    # Process the homepage's own profile links right away, then each section as
    # we discover it — saving after EACH section instead of scanning everything
    # first. That way a crash/hang in one section never loses the sections that
    # already finished, and data shows up in the DB much sooner.
    async def process_batch(batch_profiles, roster_models, label):
        nonlocal total_saved
        if batch_profiles:
            print(f"  [{label}] Crawling {len(batch_profiles)} profile page(s) for photos + measurements...")
            await crawl_profiles_directly(batch_profiles, name, roster_models, force=force)
        else:
            # No profile pages — keep only roster rows that actually have data
            keep = [m for m in roster_models if m.get("english") and any(m.get(f) for f in ("height", "chest", "waist", "hips"))]
            if keep:
                total_saved += save_crawled_models(keep, name)
        # crawl_profiles_directly already saves each profile immediately, so just
        # report how many of this batch are now in the DB
        print(f"  [{label}] Done.")

    if profile_urls:
        await process_batch(profile_urls, models, "homepage")
    elif models:
        await process_batch([], models, "homepage")

    if roster_urls:
        print(f"  Found {len(roster_urls)} roster section(s): {roster_urls[:8]}")
        for roster_url in roster_urls[:8]:
            label = roster_url.rstrip("/").split("/")[-1] or roster_url
            print(f"  Crawling section: {roster_url}")
            try:
                sub_models, sub_profiles = await crawl_roster_section(roster_url, name)
            except Exception as e:
                print(f"  Section {label} failed: {e} — skipping, keeping earlier sections")
                continue
            new_models = [m for m in sub_models if m.get("english", "").strip().upper() not in seen_names]
            new_profiles = [p for p in sub_profiles if p not in seen_profiles]
            print(f"  AI found {len(new_models)} new model(s), {len(new_profiles)} new profile link(s) in {label}/")
            for m in new_models:
                seen_names.add(m["english"].strip().upper())
            seen_profiles.update(new_profiles)
            all_profile_urls.extend(new_profiles)
            # Save this section's people now, before moving to the next section
            await process_batch(new_profiles, new_models, label)

    # Flag models we'd previously crawled who no longer appear anywhere on the site
    if all_profile_urls:
        previously_known = database.get_existing_profile_urls(name)
        current_urls = set(all_profile_urls)
        gone_ids = [m["id"] for url_, m in previously_known.items() if url_ not in current_urls]
        if gone_ids:
            database.set_models_active(gone_ids, active=False)
            print(f"  Marked {len(gone_ids)} model(s) inactive (no longer found on site)")

    update_last_crawled(agency["id"])
    print(f"  Finished {name}.")
    return len(seen_profiles)


async def main(url_override=None, force=False):
    database.init_db()

    if url_override:
        from urllib.parse import urlparse
        host = urlparse(url_override).netloc.replace("www.", "")
        # Reuse the agency the user already registered (match by website host) so
        # models stay tagged under the registered name and last_crawled updates.
        registered = database.get_agency_by_website(host)
        if registered:
            agency = {
                "id": registered["id"],
                "agency_name": registered["agency_name"],
                "agency_website": url_override,
            }
            print(f"Using registered agency: {registered['agency_name']} (id {registered['id']})")
        else:
            name_map = {
                "jmodelmanagement.co.kr": "J Model Management",
                "morphmgmt.com": "MORPH Management",
                "models.com": "Models.com",
            }
            agency_name = name_map.get(host, host)
            agency = {"id": 0, "agency_name": agency_name, "agency_website": url_override}
            print(f"No registered agency for {host}; using name '{agency_name}'")
        await crawl_agency(agency, force=force)
        return

    agencies = get_agencies_to_crawl()
    if not agencies:
        print("No agencies need crawling right now.")
        return

    print(f"Found {len(agencies)} agencies to crawl.")
    total = 0
    for agency in agencies:
        total += await crawl_agency(agency, force=force)

    print(f"\nDone. Total models found: {total}")


def backfill_photos():
    """One-time script: download all external photo URLs in the DB to local storage
    and update the photo_url to the local path. Run with:
        python crawler.py --backfill-photos
    Safe to re-run — skips models that already have a local photo."""
    import re as _re
    conn = database.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, english, photo_url FROM models WHERE photo_url != '' AND photo_url NOT LIKE '/static/%'")
        rows = cur.fetchall()
    conn.close()

    print(f"Backfilling photos for {len(rows)} models...")
    for row in rows:
        model_id = row["id"] or _re.sub(r'[^a-z0-9]+', '_', row["english"].lower()).strip('_')
        local_url = download_photo(row["photo_url"], model_id)
        if local_url != row["photo_url"]:
            conn = database.get_connection()
            with conn.cursor() as cur:
                cur.execute("UPDATE models SET photo_url = %s WHERE id = %s", (local_url, row["id"]))
            conn.commit()
            conn.close()
            print(f"  ✓ {row['english']} → {local_url}")
        else:
            print(f"  ✗ {row['english']} — download failed, keeping external URL")
    print("Backfill done.")


if __name__ == "__main__":
    if "--backfill-photos" in sys.argv:
        database.init_db()
        backfill_photos()
    else:
        args = [a for a in sys.argv[1:] if a != "--force"]
        force = "--force" in sys.argv
        url = args[0] if args else None
        asyncio.run(main(url, force=force))
