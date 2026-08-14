"""
Benchmark and concurrency test for the Akamai solver.
Usage:
  python benchmark.py <email> <password> [workers] [rounds]

  workers: number of concurrent workers (default: 1)
  rounds:  total solves to run (default: workers)
"""
import os
import sys
import time
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ.setdefault("SOLVER", "jsdom")

from solver_jsdom import solve, _log


def timed_solve(email, password, worker_id):
    t0 = time.time()
    _log(f"[W{worker_id}] Starting solve")
    result = solve(email, password)
    dt = time.time() - t0
    result["elapsed"] = round(dt, 1)
    result["worker"] = worker_id
    _log(f"[W{worker_id}] Done in {dt:.1f}s — {result.get('status', '?')}")
    return result


def run_benchmark(email, password, workers=1, rounds=None):
    if rounds is None:
        rounds = workers

    print(f"\n{'='*60}")
    print(f"Benchmark: {rounds} solve(s), {workers} concurrent worker(s)")
    print(f"{'='*60}\n")

    results = []
    t_start = time.time()

    stagger = float(os.environ.get("STAGGER", "0"))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for i in range(rounds):
            f = pool.submit(timed_solve, email, password, i + 1)
            futures[f] = i + 1
            if stagger > 0 and i < rounds - 1:
                time.sleep(stagger)

        for f in as_completed(futures):
            wid = futures[f]
            try:
                r = f.result()
                results.append(r)
            except Exception as e:
                results.append({
                    "success": False, "error": str(e),
                    "elapsed": 0, "worker": wid,
                })

    t_total = time.time() - t_start

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")

    successes = [r for r in results if r.get("status") == 401 or r["success"]]
    failures = [r for r in results if r.get("status") != 401 and not r["success"]]
    times = [r["elapsed"] for r in results]

    print(f"Total time:    {t_total:.1f}s")
    print(f"Rounds:        {rounds}")
    print(f"Workers:       {workers}")
    print(f"Bypassed:      {len(successes)}/{rounds} ({100*len(successes)/rounds:.0f}%)")
    print(f"Failed:        {len(failures)}/{rounds}")

    if times:
        print(f"\nPer-solve timing:")
        print(f"  Min:         {min(times):.1f}s")
        print(f"  Max:         {max(times):.1f}s")
        print(f"  Mean:        {statistics.mean(times):.1f}s")
        if len(times) > 1:
            print(f"  Median:      {statistics.median(times):.1f}s")
            print(f"  Stdev:       {statistics.stdev(times):.1f}s")

    print(f"\nThroughput:    {rounds/t_total:.2f} solves/sec")
    if workers > 1 and times:
        print(f"Speedup:       {statistics.mean(times) * rounds / t_total:.1f}x vs sequential")

    print(f"\nPer-solve results:")
    for r in sorted(results, key=lambda x: x["worker"]):
        status = r.get("status", "?")
        bypass = "BYPASS" if status == 401 or r["success"] else "FAIL"
        print(f"  W{r['worker']:02d}: {bypass} ({status}) in {r['elapsed']:.1f}s"
              + (f" — {r.get('error', '')[:60]}" if not r["success"] and r.get("error") else ""))

    return results


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python benchmark.py <email> <password> [workers] [rounds]")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    rounds = int(sys.argv[4]) if len(sys.argv) > 4 else workers

    run_benchmark(email, password, workers, rounds)
