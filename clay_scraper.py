"""
Open Clay in a stealth Chromium session, sign up, and prepare to process
CSV batches from a local leads folder.

Secrets and paths come from the environment. Do not hardcode API keys.
"""

import asyncio
import os
import random
import unicodedata
from pathlib import Path

import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

SOURCE_DIR = Path(os.environ.get("LEADS_SOURCE_DIR", r"D:\LEADS CSV"))
OUTPUT_BASE = Path(os.environ.get("LEADS_OUTPUT_DIR", r"D:\LEADS\archieved leads"))
CONCURRENT_CONTEXTS = int(os.environ.get("CLAY_CONCURRENT", "2"))
ENROLL_URL = os.environ.get("CLAY_SIGNUP_URL", "https://app.clay.com/signup")
TEMPLATE_URL = os.environ.get("CLAY_TEMPLATE_URL", "")
PROXY_API_KEY = os.environ.get("WEBSHARE_API_KEY", "")
EMAIL_DOMAIN = os.environ.get("CLAY_EMAIL_DOMAIN", "example.com")
SIGNUP_PASSWORD = os.environ.get("CLAY_SIGNUP_PASSWORD", "")
USED_PROXIES = set()


def pending_csvs():
    if not SOURCE_DIR.exists():
        print(f"[Leads] Source folder does not exist: {SOURCE_DIR}")
        return []
    files = sorted(SOURCE_DIR.glob("*.csv"))
    print(f"[Leads] Found {len(files)} CSV files in {SOURCE_DIR}")
    for path in files:
        print(f"  - {path.name}")
    return files


def sanitize_name(name):
    ascii_only = unicodedata.normalize("NFKD", name).encode("ASCII", "ignore").decode("utf-8")
    return "".join(c for c in ascii_only if c.isalnum())


async def get_user_agent(playwright):
    device = playwright.devices.get("Desktop Chrome", {})
    ua = device.get("user_agent", "")
    return ua + f" Custom/{random.randint(1000, 9999)}"


def get_random_proxy_credentials():
    if not PROXY_API_KEY:
        print("[Proxy API] WEBSHARE_API_KEY is not set; launching without a proxy.")
        return None
    try:
        headers = {"Authorization": f"Token {PROXY_API_KEY}"}
        response = httpx.get(
            "https://proxy.webshare.io/api/proxy/list/?mode=direct&page_size=20",
            headers=headers,
            timeout=15,
        )
        if response.status_code == 200:
            proxies = response.json().get("results", [])
            for proxy in proxies:
                proxy_id = proxy.get("id")
                if not proxy_id or proxy_id in USED_PROXIES:
                    continue
                USED_PROXIES.add(proxy_id)
                return {
                    "id": proxy_id,
                    "server": f"http://{proxy['proxy_address']}:{proxy['ports']['http']}",
                    "username": proxy["username"],
                    "password": proxy["password"],
                }
    except Exception as e:
        print(f"[Proxy API] Error: {e}")
    return None


def test_proxy(proxy):
    try:
        auth = f"{proxy['username']}:{proxy['password']}@"
        proxies = {
            "http": proxy["server"].replace("http://", f"http://{auth}"),
            "https": proxy["server"].replace("http://", f"http://{auth}"),
        }
        r = httpx.get("https://app.clay.com/signup", proxies=proxies, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


async def new_context(stealth, playwright):
    working_proxy = None
    for _ in range(5):
        proxy_config = get_random_proxy_credentials()
        if proxy_config and test_proxy(proxy_config):
            working_proxy = proxy_config
            break

    launch_opts = {
        "headless": False,
        "slow_mo": 100,
    }
    if working_proxy:
        launch_opts["proxy"] = {
            "server": working_proxy["server"],
            "username": working_proxy["username"],
            "password": working_proxy["password"],
        }

    browser = await playwright.chromium.launch(**launch_opts)

    locales = ["en-US", "en-GB", "fr-FR", "de-DE", "es-ES"]
    timezones = ["America/New_York", "Europe/Berlin", "Asia/Kolkata", "Asia/Singapore"]
    color_schemes = ["light", "dark"]
    scale_factors = [1.0, 1.25, 1.5, 2.0]

    context = await browser.new_context(
        viewport={"width": 1280 + random.randint(-100, 100), "height": 720 + random.randint(-100, 100)},
        user_agent=await get_user_agent(playwright),
        locale=random.choice(locales),
        timezone_id=random.choice(timezones),
        device_scale_factor=random.choice(scale_factors),
        color_scheme=random.choice(color_schemes),
        permissions=["geolocation"],
        geolocation={
            "latitude": 37.7749 + random.uniform(-0.5, 0.5),
            "longitude": -122.4194 + random.uniform(-0.5, 0.5),
        },
    )

    await stealth.apply_stealth_async(context)
    page = await context.new_page()
    print("[Stealth+Proxy] Launched browser with stealth and randomized fingerprint")
    return browser, context, page


async def run_enrichment(run_index: int, processed_files: set):
    stealth = Stealth()
    async with stealth.use_async(async_playwright()) as pw:
        browser, context, page = await new_context(stealth, pw)

        csvs = [p for p in pending_csvs() if p.name not in processed_files]
        if csvs:
            print(f"[{run_index}] Next unprocessed file: {csvs[0].name}")
        else:
            print(f"[{run_index}] No unprocessed CSVs in {SOURCE_DIR}")

        print(f"[{run_index}] Opening Clay signup")
        try:
            await page.goto(ENROLL_URL, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"[{run_index}] ERROR: navigation failed: {e}")
            await context.close()
            await browser.close()
            return

        print(f"[{run_index}] Filling signup form")
        req_ctx = await pw.request.new_context()
        resp = await req_ctx.get("https://randomuser.me/api/")
        data = await resp.json()
        await req_ctx.dispose()

        first = sanitize_name(data["results"][0]["name"]["first"].capitalize())
        last = sanitize_name(data["results"][0]["name"]["last"].capitalize())
        email = f"{first.lower()}.{last.lower()}{random.randint(100, 999)}@{EMAIL_DOMAIN}"

        try:
            await page.wait_for_selector('input[placeholder="Full name"]', timeout=10000)
            await page.fill('input[placeholder="Full name"]', f"{first} {last}")
            await page.fill('input[placeholder="Email address"]', email)
        except PlaywrightTimeoutError:
            print(f"[{run_index}] ERROR: Name/email input field not found.")
            debug_file = f"debug-{run_index}.html"
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(await page.content())
            print(f"[{run_index}] Saved debug HTML to {debug_file}")
            await context.close()
            await browser.close()
            return

        if not SIGNUP_PASSWORD:
            print(f"[{run_index}] ERROR: set CLAY_SIGNUP_PASSWORD before running.")
            await context.close()
            await browser.close()
            return

        await page.click('button:has-text("Continue")')
        await page.wait_for_selector('input[type="password"]')
        await page.fill('input[type="password"]', SIGNUP_PASSWORD)
        await page.click('button:has-text("Continue")')

        print(f"[{run_index}] Awaiting email verification for {email}...")
        if TEMPLATE_URL:
            print(f"[{run_index}] Template URL after verify: {TEMPLATE_URL}")
        print(f"[{run_index}] Output folder: {OUTPUT_BASE}")
        input(f"[{run_index}] After verifying email, press Enter to continue...")

        await context.close()
        await browser.close()


async def main():
    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    pending_csvs()
    processed = set()
    for i in range(CONCURRENT_CONTEXTS):
        await run_enrichment(i + 1, processed)


if __name__ == "__main__":
    asyncio.run(main())
