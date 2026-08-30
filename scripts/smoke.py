"""Loopback smoke test for the standard local/demo port."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

PORT = int(os.environ.get("PCP_PORT", "8102"))
BASE_URL = f"http://127.0.0.1:{PORT}"


def request(path: str, payload: dict | None = None) -> tuple[int, bytes]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    incoming = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(incoming, timeout=3) as response:
        return response.status, response.read()


def wait_for_health() -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            status, body = request("/api/v1/health")
            if status == 200 and json.loads(body)["status"] == "healthy":
                return
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            time.sleep(0.25)
    raise RuntimeError(f"service did not become healthy on {BASE_URL}")


def main() -> None:
    wait_for_health()
    for path, marker in (
        ("/", b"Optimize recommendations"),
        ("/index.html", b"Optimize recommendations"),
        ("/dashboard", b"Operator Dashboard"),
        ("/dashboard.html", b"Operator Dashboard"),
        ("/architecture", b"One governed decision loop"),
        ("/architecture.html", b"One governed decision loop"),
    ):
        status, body = request(path)
        if status != 200 or marker not in body:
            raise RuntimeError(f"unexpected response from {path}")

    status, body = request(
        "/api/v1/recommendations/rank",
        {
            "request_id": "req-smoke-8102",
            "subject_id": "subject-smoke-8102",
            "domain": "commerce",
            "purpose": "help people find useful products they are likely to value",
            "consent": True,
            "cohort_id": "cohort-commerce-returning",
            "candidates": [
                {
                    "id": "item-smoke-a",
                    "features": {
                        "relevance": 0.9,
                        "quality": 0.9,
                        "user_value": 0.8,
                        "diversity": 0.7,
                        "freshness": 0.6,
                        "satisfaction": 0.8,
                        "safety": 0.99,
                    },
                },
                {
                    "id": "item-smoke-b",
                    "features": {
                        "relevance": 0.8,
                        "quality": 0.85,
                        "user_value": 0.9,
                        "diversity": 0.8,
                        "freshness": 0.7,
                        "satisfaction": 0.8,
                        "safety": 0.98,
                    },
                },
            ],
        },
    )
    result = json.loads(body)
    if status != 200 or len(result.get("recommendations", [])) != 2:
        raise RuntimeError("rank smoke request did not return two recommendations")
    if result.get("governance", {}).get("consent") != "verified":
        raise RuntimeError("rank smoke request did not enforce consent")


if __name__ == "__main__":
    main()
