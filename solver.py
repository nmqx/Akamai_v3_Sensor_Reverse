"""
Akamai BM v2 Solver for Basic-Fit — entry point.
Default: solver_jsdom (pure API, no browser, ~5MB per session).
Fallback: solver_pool (shared Playwright browser, ~20MB per session).
Backup: solver_api (new browser per solve, ~150MB per session).

Set SOLVER env var to pick: jsdom, pool, api
"""
import os
import sys

_solver = os.environ.get("SOLVER", "jsdom").lower()
_pool = False

if _solver == "pool":
    from solver_pool import solve, BrowserPool
    _pool = True
elif _solver == "api":
    from solver_api import solve
else:
    try:
        from solver_jsdom import solve
    except ImportError:
        from solver_pool import solve, BrowserPool
        _pool = True


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

    if _pool:
        BrowserPool.get().close()
