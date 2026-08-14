"""Check if proxy sessions give different exit IPs."""
import os
import random
import threading
from curl_cffi import requests as cffi_requests

PROXY_USER = os.environ.get("PROXY_USER", "")
PROXY_PASS = os.environ.get("PROXY_PASS", "")

results = {}

def check_ip(wid):
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    sid = "".join(random.choice(chars) for _ in range(6))
    proxy = f"http://{PROXY_USER}-country-FR-session-{sid}-time-1:{PROXY_PASS}@eu.nettify.xyz:8080"
    s = cffi_requests.Session(impersonate="chrome131", proxies={"https": proxy, "http": proxy})
    r = s.get("https://httpbin.org/ip")
    results[wid] = {"ip": r.json()["origin"], "session": sid}

threads = [threading.Thread(target=check_ip, args=(i,)) for i in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()

for wid in sorted(results):
    print(f"Worker {wid}: IP={results[wid]['ip']} session={results[wid]['session']}")

ips = [r["ip"] for r in results.values()]
print(f"\nUnique IPs: {len(set(ips))}/{len(ips)}")
print(f"All different: {len(set(ips)) == len(ips)}")
