"""
Optimized Akamai BM v2 Solver for Basic-Fit — shared browser pool.
All HTTP via curl_cffi. One persistent Chrome process shared across solves.
Each solve creates a lightweight browser context (~20MB) instead of a new
browser (~150MB).

Memory per concurrent session: ~20MB (vs ~150MB with solver_api.py)

Requirements:
  pip install curl_cffi playwright playwright-stealth
  playwright install chrome
"""
import json
import os
import random
import sys
import time
import threading
from urllib.parse import urlparse

from curl_cffi import requests as cffi_requests
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth


BASE_URL = "https://login.basic-fit.com"
LOGIN_URL = (
    f"{BASE_URL}/"
    "?client_id=5T2sVjv1ViH1FExCeRsXuT4EeLw91au1D2kpQS_4T3o"
    "&redirect_uri=https%3A%2F%2Fmy.basic-fit.com%2Fsso"
    "&response_type=code&state=cmV0dXJsOi8"
)
PROXY_USER = os.environ.get("PROXY_USER", "")
PROXY_PASS = os.environ.get("PROXY_PASS", "")
PROXY_HOST = os.environ.get("PROXY_HOST", "eu.nettify.xyz")
PROXY_PORT = os.environ.get("PROXY_PORT", "8080")
PROXY_TEMPLATE = (
    f"http://{PROXY_USER}-country-FR-session-{{session}}-time-1"
    f":{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
)
MAX_ATTEMPTS = 3
SOLVER_TYPE = "pool"

BLOCKED_DOMAINS = {
    "googletagmanager.com", "google-analytics.com", "analytics.google.com",
    "consent.cookiebot.com", "consentcdn.cookiebot.com",
    "gstatic.com", "fonts.googleapis.com", "fonts.gstatic.com",
    "cdn.cookielaw.org", "bat.bing.com",
    "facebook.com", "connect.facebook.net",
    "doubleclick.net", "googlesyndication.com",
    "sentry.io", "newrelic.com", "nr-data.net",
    "bam.nr-data.net", "js-agent.newrelic.com",
    "akamai.com",
}
BLOCKED_EXT = frozenset((".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
                          ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".webp"))


class BrowserPool:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._pw = None
        self._browser = None
        self._ua = None

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                cls._instance._start()
            return cls._instance

    def _start(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True, channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        temp_ctx = self._browser.new_context()
        temp_page = temp_ctx.new_page()
        self._ua = temp_page.evaluate("() => navigator.userAgent").replace(
            "HeadlessChrome", "Chrome"
        )
        temp_ctx.close()

    @property
    def browser(self):
        return self._browser

    @property
    def ua(self):
        return self._ua

    def new_context(self):
        return self._browser.new_context(
            user_agent=self._ua,
            viewport={"width": 1600, "height": 900},
            locale="fr-FR", timezone_id="Europe/Paris",
            color_scheme="light",
        )

    def close(self):
        with self._lock:
            if self._browser:
                self._browser.close()
                self._browser = None
            if self._pw:
                self._pw.stop()
                self._pw = None
            BrowserPool._instance = None


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def _make_proxy():
    sid = f"{random.randint(100000, 999999):06d}"
    url = PROXY_TEMPLATE.format(session=sid)
    return url, sid


def solve(email: str, password: str) -> dict:
    result = {"success": False, "error": "no attempts"}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        proxy_url, proxy_sid = _make_proxy()
        _log(f"Attempt {attempt}/{MAX_ATTEMPTS} (proxy {proxy_sid})")
        try:
            result = _attempt(email, password, proxy_url)
            if result["success"]:
                return result
            if result.get("status") == 401:
                _log("Invalid credentials -- not retrying")
                return result
        except Exception as e:
            _log(f"Error: {e}")
            import traceback; traceback.print_exc()
            result = {"success": False, "error": str(e)}
        if attempt < MAX_ATTEMPTS:
            wait = random.uniform(3, 6)
            _log(f"Waiting {wait:.1f}s...")
            time.sleep(wait)
    return result


def _attempt(email, password, proxy_url):
    proxies = {"https": proxy_url, "http": proxy_url}
    sess = cffi_requests.Session(impersonate="chrome131", proxies=proxies)

    pool = BrowserPool.get()
    ua = pool.ua
    _log(f"  Chrome/{ua.split('Chrome/')[1][:10] if 'Chrome/' in ua else '?'}")

    ctx = pool.new_context()
    page = ctx.new_page()
    Stealth(navigator_languages_override=("fr-FR", "fr")).apply_stealth_sync(page)

    def route_handler(route):
        _route_through_cffi(route, sess, ua)

    page.route("**/*", route_handler)

    try:
        result = _run_flow(page, ctx, sess, ua, email, password)
    finally:
        ctx.close()

    return result


def _run_flow(page, ctx, sess, ua, email, password):
    _log("  Loading login page...")
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    except Exception as e:
        _log(f"  Page load warning: {type(e).__name__}")
    time.sleep(3)
    _log(f"  trust={_get_trust(sess)}")

    _log("  Building trust...")
    _mouse_activity(page, rounds=6)
    for _ in range(15):
        if _get_trust(sess) == "0":
            break
        _mouse_activity(page, rounds=3)
        time.sleep(1)
    _log(f"  trust={_get_trust(sess)}")

    csrf = sess.cookies.get("_csrf", "")
    login_headers = _login_headers(ua, csrf, LOGIN_URL)

    _log("  Login POST...")
    r = sess.post(
        f"{BASE_URL}/login",
        json={"email": email, "password": password, "keepLoggedIn": False},
        headers=login_headers,
    )
    _log(f"  Status: {r.status_code}")

    if r.status_code == 200:
        return _success_result(r, sess)
    if r.status_code == 401:
        _log("  401 - Akamai bypassed (credentials rejected)")
        return {"success": False, "status": 401, "body": r.text[:500]}
    if r.status_code != 428:
        return {"success": False, "status": r.status_code, "body": r.text[:500],
                "error": f"unexpected status {r.status_code}"}

    challenge = r.json()
    chlge_url = challenge.get("chlge_content_url", "")
    verify_url = challenge.get("verify_url", "")
    _log("  428 challenge, solving...")

    try:
        page.goto(f"{BASE_URL}{chlge_url}", wait_until="domcontentloaded", timeout=30_000)
    except:
        pass
    time.sleep(2)
    _log(f"  Challenge: trust={_get_trust(sess)}, sec_cpt={_get_sec_cpt(sess)}")

    _mouse_activity(page, rounds=6)
    for _ in range(12):
        if _get_sec_cpt(sess) == "2":
            break
        _mouse_activity(page, rounds=3)
        time.sleep(1)

    if _get_sec_cpt(sess) != "2":
        _log(f"  sec_cpt didn't reach 2 (got {_get_sec_cpt(sess)})")
        return {"success": False, "error": "challenge sensor failed",
                "trust": _get_trust(sess), "sec_cpt": _get_sec_cpt(sess)}

    if verify_url:
        _log("  Verify POST...")
        r_v = sess.post(
            f"{BASE_URL}/{verify_url}",
            data=json.dumps({"sensor_data": ""}),
            headers={
                "Accept": "*/*",
                "Content-Type": "text/plain;charset=UTF-8",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}{chlge_url}",
                "User-Agent": ua,
            },
        )
        _log(f"  Verify: {r_v.status_code}, sec_cpt={_get_sec_cpt(sess)}")

    time.sleep(2)

    csrf = sess.cookies.get("_csrf", csrf)
    login_headers = _login_headers(ua, csrf, LOGIN_URL)

    _log("  Retry login POST...")
    r2 = sess.post(
        f"{BASE_URL}/login",
        json={"email": email, "password": password, "keepLoggedIn": False},
        headers=login_headers,
    )
    _log(f"  Retry: {r2.status_code}, trust={_get_trust(sess)}, sec_cpt={_get_sec_cpt(sess)}")

    if r2.status_code == 200:
        return _success_result(r2, sess)
    if r2.status_code == 401:
        _log("  401 - Akamai bypassed after challenge!")
        return {"success": False, "status": 401, "body": r2.text[:500]}

    return {
        "success": False,
        "status": r2.status_code,
        "body": r2.text[:500],
        "error": "challenge solve failed",
    }


def _route_through_cffi(route, sess, ua):
    req = route.request
    url = req.url

    if url.startswith(("data:", "blob:")):
        route.continue_()
        return

    parsed = urlparse(url)
    domain = parsed.hostname or ""
    path = parsed.path.lower()

    if any(d in domain for d in BLOCKED_DOMAINS):
        route.abort()
        return
    if any(path.endswith(ext) for ext in BLOCKED_EXT):
        route.abort()
        return

    method = req.method
    headers = {k: v for k, v in req.headers.items() if not k.startswith(":")}

    try:
        if method == "GET":
            r = sess.get(url, headers=headers, allow_redirects=True, timeout=30)
        elif method == "POST":
            body = req.post_data or ""
            r = sess.post(url, data=body.encode("utf-8") if isinstance(body, str) else body,
                         headers=headers, allow_redirects=True, timeout=30)
        elif method == "OPTIONS":
            r = sess.options(url, headers=headers, timeout=30)
        else:
            route.abort()
            return

        resp_headers = {}
        for k, v in r.headers.items():
            if k.lower() not in ("content-encoding", "transfer-encoding", "content-length"):
                resp_headers[k] = v

        route.fulfill(status=r.status_code, headers=resp_headers, body=r.content)

    except Exception:
        route.abort()


def _mouse_activity(page, rounds=6):
    for _ in range(rounds):
        page.mouse.move(
            random.randint(200, 1400),
            random.randint(100, 800),
            steps=random.randint(8, 20),
        )
        time.sleep(random.uniform(0.3, 0.6))


def _login_headers(ua, csrf, referer):
    h = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": BASE_URL,
        "Referer": referer,
        "User-Agent": ua,
        "client-id": "5T2sVjv1ViH1FExCeRsXuT4EeLw91au1D2kpQS_4T3o",
        "redirect-uri": "https://my.basic-fit.com/sso",
        "response-type": "code",
    }
    if csrf:
        h["x-csrf-token"] = csrf
    return h


def _get_trust(sess):
    abck = sess.cookies.get("_abck", "")
    return abck.split("~")[1] if "~" in abck else "?"


def _get_sec_cpt(sess):
    sc = sess.cookies.get("sec_cpt", "")
    return sc.split("~")[1] if sc and "~" in sc else "none"


def _success_result(r, sess):
    _log("  SUCCESS!")
    return {
        "success": True,
        "status": 200,
        "body": r.text[:500],
        "cookies": dict(sess.cookies),
    }


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        em, pw = sys.argv[1], sys.argv[2]
    else:
        em = input("Email: ").strip()
        pw = input("Password: ").strip()

    result = solve(em, pw)

    print(f"\n{'='*60}")
    print(f"Result: {'SUCCESS' if result['success'] else 'FAILED'}")
    for k, v in result.items():
        if k == "cookies":
            print(f"  cookies: {list(v.keys())}")
        elif k != "success":
            print(f"  {k}: {str(v)[:200]}")

    BrowserPool.get().close()
