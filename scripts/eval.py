"""Measure retrieval accuracy and latency against a running API.

    uvicorn app.main:app        # in another terminal
    python -m scripts.eval             # full run
    python -m scripts.eval --delay 20  # slower, for tight free-tier quota

Each case asserts the answer contains an expected string, and (for prose
questions) that the expected document was cited. Accuracy is the pass rate.
"""

import argparse
import statistics
import time
import urllib.error
import urllib.request
import json

API = "http://127.0.0.1:8000/ask"

# question, must appear in answer (lowercase), must appear in cited docs (optional)
CASES = [
    ("Does Gaurang know Solidity?", "yes", None),
    ("Does he know Rust?", "no evidence", None),
    ("Does he know Kubernetes?", "no evidence", None),
    ("Does he know PyTorch?", "yes", None),
    ("What is the GitHub link for his Work Memory project?", "github.com", None),
    ("Tell me about King of the Pot", "base", None),
    ("What tech does FluxLLM use?", "fastapi", None),
    ("Show his blockchain projects", "king of the pot", None),
    ("What machine learning projects has he built?", "work memory", None),
    ("Summarize his experience", "tychi", "about"),
    ("Where did he study?", "bennett", "about"),
    ("What did he do at Tychi Labs?", "erc-3009", "about"),
]


def ask(question: str) -> tuple[dict, float]:
    body = json.dumps({"question": question}).encode()
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}
    )
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.load(response)
    return payload, time.perf_counter() - start


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=8.0, help="seconds between calls")
    args = parser.parse_args()

    passed, latencies = 0, []
    for question, expect_answer, expect_doc in CASES:
        try:
            payload, elapsed = ask(question)
        except urllib.error.HTTPError as exc:
            print(f"FAIL  {question}\n      HTTP {exc.code} {exc.read()[:120]!r}")
            continue

        latencies.append(elapsed)
        answer = payload["answer"].lower()
        docs = " ".join(s["document"].lower() for s in payload["sources"])

        ok = expect_answer in answer and (expect_doc is None or expect_doc in docs)
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {elapsed:5.2f}s  {question}")
        if not ok:
            print(f"      got: {payload['answer'][:110]}")

        time.sleep(args.delay)

    if not latencies:
        print("\nNo successful calls.")
        return

    ordered = sorted(latencies)
    p95 = ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)]
    print(f"\nAccuracy: {passed}/{len(CASES)} ({100 * passed / len(CASES):.0f}%)")
    print(f"Latency:  median {statistics.median(latencies):.2f}s  p95 {p95:.2f}s")


if __name__ == "__main__":
    main()
