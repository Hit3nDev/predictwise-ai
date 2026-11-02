"""
Load test for the Auto Scaling demo (Lab 13). Standard library only.

    python infra/loadtest.py http://<load-balancer-dns> --minutes 15 --workers 12

Loads a sample dataset, then keeps the servers busy with EDA and model
training. Watch the CloudWatch dashboard: CPU climbs past the 50% target, Auto
Scaling launches more servers (they take several minutes to boot), and the
"answered by" counts below spread across more instances. Stop it and, after
the cool-down, Auto Scaling removes the extra servers again.
"""

import argparse
import json
import threading
import time
import urllib.request
from collections import Counter


def call(url, method="GET", body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("--minutes", type=float, default=15)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    dataset = call(f"{base}/samples/customers/load", "POST")["id"]
    print(f"Using dataset {dataset}. Running {args.workers} workers for {args.minutes} minutes. Ctrl+C to stop.")

    stop_at = time.time() + args.minutes * 60
    ok, failed, servers = Counter(), Counter(), Counter()
    lock = threading.Lock()

    def worker(n):
        i = 0
        while time.time() < stop_at:
            i += 1
            try:
                if (i + n) % 5 == 0:          # every fifth request trains models: the expensive one
                    call(f"{base}/datasets/{dataset}/train", "POST", {"target": "purchased"})
                    kind = "train"
                else:
                    call(f"{base}/datasets/{dataset}/eda")
                    kind = "eda"
                server = call(f"{base}/health")["server"]
                with lock:
                    ok[kind] += 1
                    servers[server] += 1
            except Exception as exc:          # keep going: errors are part of what you are measuring
                with lock:
                    failed[type(exc).__name__] += 1

    threads = [threading.Thread(target=worker, args=(n,), daemon=True) for n in range(args.workers)]
    for t in threads:
        t.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(15)
            with lock:
                print(f"[{time.strftime('%H:%M:%S')}] ok={dict(ok)} failed={dict(failed)} answered by={dict(servers)}")
    except KeyboardInterrupt:
        print("Stopping.")


if __name__ == "__main__":
    main()
