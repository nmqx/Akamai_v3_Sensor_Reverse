"""Test concurrent solves with different emails per worker."""
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ.setdefault("SOLVER", "jsdom")

from solver_jsdom import solve, _log


def worker(wid, email):
    t0 = time.time()
    _log(f"[W{wid}] Starting with {email}")
    r = solve(email, "wrongpass123")
    dt = time.time() - t0
    r["elapsed"] = round(dt, 1)
    r["worker"] = wid
    _log(f"[W{wid}] Done in {dt:.1f}s -- {r.get('status', '?')}")
    return r


if __name__ == "__main__":
    n_workers = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    emails = [f"test{i}@test{i}.com" for i in range(n_workers)]

    print(f"\n{'='*60}")
    print(f"Concurrent test: {n_workers} workers, different emails")
    print(f"{'='*60}\n")

    results = []
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(worker, i + 1, emails[i]): i + 1 for i in range(n_workers)}
        for f in as_completed(futures):
            results.append(f.result())

    t_total = time.time() - t_start

    bypassed = [r for r in results if r.get("status") == 401]
    print(f"\n{'='*60}")
    print(f"Bypassed: {len(bypassed)}/{n_workers} in {t_total:.1f}s total")
    for r in sorted(results, key=lambda x: x["worker"]):
        st = r.get("status", "?")
        err = r.get("error", "")
        print(f"  W{r['worker']}: {st} in {r['elapsed']}s" + (f" -- {err[:60]}" if err else ""))
