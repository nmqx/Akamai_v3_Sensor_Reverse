"""
Akamai BM v2 Solver for Basic-Fit (login.basic-fit.com)
Uses real Chrome (via Playwright channel="chrome") + stealth + French proxy.
The sensor script runs natively in the browser, achieving trust=0 which
bypasses the behavioral challenge entirely.

Requirements:
  pip install playwright playwright-stealth
  playwright install chrome
"""
import json
import os
import random
import sys
import time
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth


# ── Config ──────────────────────────────────────────────────────────────────

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


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def _make_proxy():
    sid = f"{random.randint(100000, 999999):06d}"
    url = PROXY_TEMPLATE.format(session=sid)
    p = urlparse(url)
    return {
        "server": f"http://{p.hostname}:{p.port}",
        "username": p.username or "",
        "password": p.password or "",
    }, sid


def solve(email: str, password: str, headless=True) -> dict:
    """
    Attempt to log in to Basic-Fit.
    Returns dict with keys: success, status, cookies, body, error
    """
    result = {"success": False, "error": "no attempts"}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        proxy_cfg, proxy_sid = _make_proxy()
        _log(f"Attempt {attempt}/{MAX_ATTEMPTS} (proxy session {proxy_sid})")

        try:
            result = _attempt(email, password, proxy_cfg, headless)
            if result["success"]:
                return result
            if result.get("status") == 401:
                _log("Invalid credentials -- not retrying")
                return result
        except Exception as e:
            _log(f"Error: {e}")
            result = {"success": False, "error": str(e)}

        if attempt < MAX_ATTEMPTS:
            wait = random.uniform(3, 6)
            _log(f"Waiting {wait:.1f}s before retry...")
            time.sleep(wait)

    return result


def _get_real_ua(browser):
    temp_ctx = browser.new_context()
    temp_page = temp_ctx.new_page()
    ua = temp_page.evaluate("() => navigator.userAgent")
    temp_ctx.close()
    return ua.replace("HeadlessChrome", "Chrome")


def _attempt(email, password, proxy_cfg, headless):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
            proxy=proxy_cfg,
        )
        real_ua = _get_real_ua(browser)
        _log(f"  Chrome UA: {real_ua.split('Chrome/')[1][:10] if 'Chrome/' in real_ua else '?'}")
        ctx = browser.new_context(
            user_agent=real_ua,
            viewport={"width": 1600, "height": 900},
            locale="fr-FR",
            timezone_id="Europe/Paris",
            color_scheme="light",
        )
        page = ctx.new_page()
        Stealth(navigator_languages_override=("fr-FR", "fr")).apply_stealth_sync(page)

        sensor_n = [0]
        page.on("request", lambda req: _inc(sensor_n) if "t2taph" in req.url else None)

        login_result = [None]
        challenge_json = [None]

        def _on_resp(resp):
            if resp.request.resource_type not in ("xhr", "fetch"):
                return
            if resp.request.method != "POST":
                return
            if not resp.url.endswith("/login"):
                return
            st = resp.status
            if st == 428:
                try:
                    challenge_json[0] = resp.json()
                except:
                    pass
            login_result[0] = {"status": st}
            try:
                login_result[0]["body"] = resp.text()[:500]
            except:
                pass

        page.on("response", _on_resp)

        def trust():
            for c in ctx.cookies():
                if c["name"] == "_abck":
                    parts = c["value"].split("~")
                    return parts[1] if len(parts) >= 2 else "?"
            return "?"

        def sec_cpt():
            for c in ctx.cookies():
                if c["name"] == "sec_cpt":
                    parts = c["value"].split("~")
                    return parts[1] if len(parts) >= 2 else "?"
            return "?"

        try:
            # 1. Load login page
            _log("  Loading login page...")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=45_000)
            _log(f"  trust={trust()}, sensors={sensor_n[0]}")

            # 2. Dismiss cookie consent + overlays
            _dismiss_overlays(page)

            # 3. Generate mouse movement to build trust
            _log("  Building trust...")
            for _ in range(6):
                page.mouse.move(
                    random.randint(300, 1200),
                    random.randint(200, 700),
                    steps=random.randint(5, 15),
                )
                time.sleep(random.uniform(0.3, 0.8))
            time.sleep(random.uniform(3, 5))

            for _ in range(20):
                if trust() == "0":
                    break
                time.sleep(1)
            _log(f"  trust={trust()}, sensors={sensor_n[0]}")

            # 4. Fill form
            _log("  Filling form...")
            _fill_form(page, email, password)
            time.sleep(random.uniform(0.5, 1.0))

            # 5. Submit
            _log("  Submitting...")
            page.evaluate("""() => {
                var btn = document.querySelector('button[type="submit"]');
                if (btn) btn.click();
            }""")
            time.sleep(6)
            _log(f"  trust={trust()}, sec_cpt={sec_cpt()}")

            # 6. Evaluate result
            result = _evaluate_result(
                page, ctx, browser, login_result, challenge_json,
                sensor_n, email, password, trust, sec_cpt
            )
            return result

        except Exception as e:
            browser.close()
            raise


def _dismiss_overlays(page):
    page.evaluate("""() => {
        document.querySelectorAll(
            '.ReactModal__Overlay, #CybotCookiebotDialog, ' +
            '#CybotCookiebotDialogBodyUnderlay, .coi-banner'
        ).forEach(function(el) { el.remove(); });
        document.body.style.overflow = 'auto';
    }""")
    try:
        btn = page.locator('#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll')
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click(timeout=3000)
            time.sleep(0.5)
    except:
        pass
    page.evaluate("""() => {
        document.querySelectorAll('.ReactModal__Overlay').forEach(function(el) { el.remove(); });
    }""")


def _fill_form(page, email, password):
    page.evaluate("""(creds) => {
        var nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        var email = document.querySelector('input[type="email"]');
        var pw = document.querySelector('input[type="password"]');
        if (email) {
            nativeSetter.call(email, creds.email);
            email.dispatchEvent(new Event('input', { bubbles: true }));
            email.dispatchEvent(new Event('change', { bubbles: true }));
        }
        if (pw) {
            nativeSetter.call(pw, creds.password);
            pw.dispatchEvent(new Event('input', { bubbles: true }));
            pw.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }""", {"email": email, "password": password})


def _evaluate_result(page, ctx, browser, login_result, challenge_json,
                     sensor_n, email, password, trust, sec_cpt):
    current_url = page.url

    # Check hostname (avoid false match on redirect_uri query param)
    hostname = urlparse(current_url).hostname or ""
    if hostname == "my.basic-fit.com":
        _log("  SUCCESS -- redirected to my.basic-fit.com!")
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
        return {"success": True, "cookies": cookies, "url": current_url}

    lr = login_result[0] or {}

    if lr.get("status") == 401:
        _log("  Invalid credentials")
        browser.close()
        return {"success": False, "status": 401, "body": lr.get("body", "")}

    # Check for 200 with redirect/code in body (OAuth success)
    if lr.get("status") == 200:
        body = lr.get("body", "")
        if body and ("code" in body or "redirect" in body.lower()):
            _log("  Login returned 200 with redirect data")
            cookies = {c["name"]: c["value"] for c in ctx.cookies()}
            browser.close()
            return {"success": True, "status": 200, "cookies": cookies, "body": body}

    # 428 challenge
    if challenge_json[0]:
        _log("  428 challenge -- solving...")
        solved = _solve_challenge(page, ctx, challenge_json[0], sensor_n)
        if solved:
            _log(f"  Post-challenge: trust={trust()}, sec_cpt={sec_cpt()}")

            # Wait for form to be ready
            try:
                page.wait_for_selector('input[type="email"]', state="visible", timeout=10_000)
            except:
                pass
            time.sleep(2)
            _dismiss_overlays(page)

            # More mouse activity for fresh trust
            for _ in range(4):
                page.mouse.move(
                    random.randint(300, 1200),
                    random.randint(200, 700),
                    steps=random.randint(5, 12),
                )
                time.sleep(random.uniform(0.3, 0.6))
            time.sleep(3)

            _fill_form(page, email, password)
            time.sleep(1)
            login_result[0] = None
            challenge_json[0] = None

            # Safer submit with null check
            page.evaluate("""() => {
                var btn = document.querySelector('button[type="submit"]');
                if (btn) btn.click();
            }""")
            time.sleep(6)
            _log(f"  Retry: trust={trust()}, sec_cpt={sec_cpt()}")

            hostname2 = urlparse(page.url).hostname or ""
            if hostname2 == "my.basic-fit.com":
                _log("  SUCCESS after challenge!")
                cookies = {c["name"]: c["value"] for c in ctx.cookies()}
                browser.close()
                return {"success": True, "cookies": cookies, "url": page.url}

            lr2 = login_result[0] or {}
            if lr2.get("status") == 401:
                _log("  401 -- credentials rejected (Akamai bypassed!)")
                browser.close()
                return {"success": False, "status": 401, "body": lr2.get("body", "")}

            if lr2.get("status") == 200:
                body = lr2.get("body", "")
                if body:
                    cookies = {c["name"]: c["value"] for c in ctx.cookies()}
                    browser.close()
                    return {"success": True, "status": 200, "cookies": cookies, "body": body}

    # Check for error messages on page
    err_text = ""
    try:
        err = page.locator('[class*="error"], [role="alert"]')
        if err.count() > 0:
            err_text = err.first.text_content()[:200]
    except:
        pass

    browser.close()
    return {
        "success": False,
        "status": lr.get("status"),
        "body": lr.get("body", ""),
        "error": err_text or "unknown outcome",
    }


def _solve_challenge(page, ctx, challenge, sensor_n):
    chlge_url = challenge.get("chlge_content_url", "")
    verify_url = challenge.get("verify_url", "")
    if not chlge_url:
        return False

    _log(f"    Navigating to challenge: {chlge_url}")
    page.goto(f"{BASE_URL}{chlge_url}", wait_until="networkidle", timeout=45_000)
    time.sleep(5)

    def trust():
        for c in ctx.cookies():
            if c["name"] == "_abck":
                parts = c["value"].split("~")
                return parts[1] if len(parts) >= 2 else "?"
        return "?"

    def sec_cpt():
        for c in ctx.cookies():
            if c["name"] == "sec_cpt":
                parts = c["value"].split("~")
                return parts[1] if len(parts) >= 2 else "?"
        return "?"

    _log(f"    Challenge: trust={trust()}, sec_cpt={sec_cpt()}, sensors={sensor_n[0]}")

    # Generate activity on challenge page to trigger sensor POSTs
    for _ in range(5):
        page.mouse.move(random.randint(200, 600), random.randint(200, 500), steps=5)
        time.sleep(random.uniform(0.3, 0.6))
    time.sleep(3)

    # Wait for sec_cpt to reach 2 (sensor data accepted)
    for _ in range(15):
        if sec_cpt() == "2":
            break
        time.sleep(1)
    _log(f"    After activity: trust={trust()}, sec_cpt={sec_cpt()}")

    if sec_cpt() != "2":
        _log("    sec_cpt didn't reach 2")
        return False

    # Call verifyStateChallenge
    page.evaluate("""() => {
        try { AKCPT.verifyStateChallenge(); } catch(e) {}
    }""")
    time.sleep(2)

    # POST to verify URL to advance sec_cpt from 2 to 3
    if verify_url:
        _log(f"    POSTing to verify URL...")
        page.evaluate("""(url) => {
            fetch('https://login.basic-fit.com/' + url, {
                method: 'POST',
                headers: {'Content-Type': 'text/plain;charset=UTF-8'},
                body: JSON.stringify({sensor_data: ''}),
                credentials: 'same-origin'
            }).catch(function(){});
        }""", verify_url)
        time.sleep(5)

    _log(f"    Post-verify: trust={trust()}, sec_cpt={sec_cpt()}")

    # Navigate back to login
    page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
    time.sleep(3)
    return True


def _inc(counter):
    counter[0] += 1


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        em, pw = sys.argv[1], sys.argv[2]
    else:
        em = input("Email: ").strip()
        pw = input("Password: ").strip()

    headless = "--visible" not in sys.argv
    result = solve(em, pw, headless=headless)

    print(f"\n{'='*60}")
    print(f"Result: {'SUCCESS' if result['success'] else 'FAILED'}")
    for k, v in result.items():
        if k == "cookies":
            print(f"  cookies: {list(v.keys())}")
        elif k != "success":
            val = str(v)[:200]
            print(f"  {k}: {val}")
