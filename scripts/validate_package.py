"""Repository-level checks that do not need third-party validation tools."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "personalization_control_plane" / "web"
SITE = ROOT / "site"

MIRRORED_FILES = (
    "index.html",
    "dashboard.html",
    "architecture.html",
    "assets/styles.css",
    "assets/site.js",
    "assets/dashboard.js",
    "assets/architecture.js",
    "assets/static-data.js",
    "assets/system-architecture.drawio",
    "assets/system-architecture.png",
    "assets/aws-reference-architecture.drawio",
    "assets/aws-reference-architecture.png",
)

FORBIDDEN_DIRECTORIES = {
    "build",
    "dist",
    "node_modules",
}

IGNORED_TREES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}

FORBIDDEN_TEXT = (
    "github.com/" + "example",
    "example" + ".com/",
    "example" + ".org/",
)


def fail(message: str) -> None:
    print(f"validation error: {message}", file=sys.stderr)
    raise SystemExit(1)


def is_ignored(path: Path) -> bool:
    return any(
        part in IGNORED_TREES or part.endswith(".egg-info")
        for part in path.relative_to(ROOT).parts
    )


def validate_mirror() -> None:
    for relative in MIRRORED_FILES:
        served = WEB / relative
        static = SITE / relative
        if not served.is_file():
            fail(f"missing served web file: {served.relative_to(ROOT)}")
        if not static.is_file():
            fail(f"missing static mirror file: {static.relative_to(ROOT)}")
        if served.read_bytes() != static.read_bytes():
            fail(f"static mirror differs: {relative}")


def validate_tree() -> None:
    for path in ROOT.rglob("*"):
        if is_ignored(path):
            continue
        if path == ROOT / "data" or ROOT / "data" in path.parents:
            continue
        if path.is_dir() and path.name in FORBIDDEN_DIRECTORIES:
            fail(f"forbidden generated directory: {path.relative_to(ROOT)}")
        if path.is_file() and (
            path.suffix in {".db", ".sqlite", ".sqlite3", ".pyc"}
            or path.name.endswith(("-wal", "-shm"))
        ):
            fail(f"forbidden generated file: {path.relative_to(ROOT)}")


def validate_text() -> None:
    text_extensions = {
        ".css",
        ".html",
        ".js",
        ".json",
        ".md",
        ".py",
        ".sh",
        ".toml",
        ".yaml",
        ".yml",
    }
    for path in ROOT.rglob("*"):
        if is_ignored(path) or not path.is_file() or path.suffix not in text_extensions:
            continue
        content = path.read_text(encoding="utf-8", errors="replace").lower()
        for forbidden in FORBIDDEN_TEXT:
            if forbidden in content:
                fail(f"placeholder public URL in {path.relative_to(ROOT)}")


def validate_standard_port() -> None:
    required = {
        "src/personalization_control_plane/cli.py",
        ".env.example",
        "Dockerfile",
        "docker-compose.yml",
        "README.md",
        "QUICKSTART.md",
        "docs/DEMO.md",
        "docs/DEPLOYMENT.md",
        "scripts/demo.sh",
        "scripts/smoke.py",
        "scripts/smoke.sh",
    }
    for relative in required:
        path = ROOT / relative
        if not path.is_file():
            fail(f"missing integration artifact: {relative}")
        if "8102" not in path.read_text(encoding="utf-8"):
            fail(f"standard port 8102 missing from {relative}")


def validate_uv_deployment() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    required = (
        "FROM python:3.12-alpine3.24@sha256:",
        "COPY --from=ghcr.io/astral-sh/uv:0.10.7@sha256:",
        "RUN apk upgrade --no-cache",
        "COPY pyproject.toml uv.lock README.md LICENSE ./",
        "uv sync --frozen --no-dev --no-editable",
        "USER pcp",
        '"uv", "run", "--frozen", "--no-dev", "--no-sync"',
    )
    for snippet in required:
        if snippet not in dockerfile:
            fail(f"Docker deployment is missing required uv configuration: {snippet}")
    if "pip install" in dockerfile:
        fail("Docker deployment must install through uv, not pip")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    if "${PCP_BIND_ADDRESS:-127.0.0.1}:${PCP_PORT:-8102}:8102" not in compose:
        fail("Compose must bind the unauthenticated demo to loopback by default")


def main() -> None:
    validate_mirror()
    validate_tree()
    validate_text()
    validate_standard_port()
    validate_uv_deployment()
    print(
        "Static mirror, repository hygiene, metadata, port, and uv deployment "
        "checks passed."
    )


if __name__ == "__main__":
    main()
