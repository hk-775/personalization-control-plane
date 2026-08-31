from __future__ import annotations

import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path


def load_validator():
    path = Path(__file__).resolve().parents[1] / "scripts" / "validate_package.py"
    spec = importlib.util.spec_from_file_location("validate_package", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validator_ignores_local_virtual_environment(tmp_path, monkeypatch) -> None:
    validator = load_validator()
    monkeypatch.setattr(validator, "ROOT", tmp_path)

    dependency = tmp_path / ".venv" / "lib" / "python" / "site-packages"
    dependency.mkdir(parents=True)
    (dependency / "dependency.py").write_text(
        'DOCUMENTATION = "https://'
        + "example"
        + '.com/"\n',
        encoding="utf-8",
    )
    cache = dependency / "__pycache__"
    cache.mkdir()
    (cache / "dependency.pyc").write_bytes(b"generated")
    local_cache = tmp_path / "__pycache__"
    local_cache.mkdir()
    (local_cache / "project.pyc").write_bytes(b"generated")

    validator.validate_tree()
    validator.validate_text()


def test_public_architecture_artifacts_are_valid_and_mirrored() -> None:
    root = Path(__file__).resolve().parents[1]
    for stem in ("system-architecture", "aws-reference-architecture"):
        site_drawio = root / "site" / "assets" / f"{stem}.drawio"
        served_drawio = (
            root
            / "src"
            / "personalization_control_plane"
            / "web"
            / "assets"
            / f"{stem}.drawio"
        )
        site_png = root / "site" / "assets" / f"{stem}.png"
        served_png = (
            root
            / "src"
            / "personalization_control_plane"
            / "web"
            / "assets"
            / f"{stem}.png"
        )

        assert ET.parse(site_drawio).getroot().tag == "mxfile"
        assert site_drawio.read_bytes() == served_drawio.read_bytes()
        assert site_png.read_bytes() == served_png.read_bytes()
        png = site_png.read_bytes()
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert png[12:16] == b"IHDR"
        assert int.from_bytes(png[16:20], "big") >= 1600
        assert int.from_bytes(png[20:24], "big") >= 800


def test_publication_documents_and_pages_workflow_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    required = (
        "STARTUP.md",
        "launch-materials.md",
        "docs/PRODUCTION_READINESS.md",
        "docs/PUBLICATION_ARTIFACTS.md",
        "docs/THREAT_MODEL.md",
        ".github/workflows/pages.yml",
        "scripts/test_public_site.mjs",
        ".github/CODEOWNERS",
        "CITATION.cff",
        "GOVERNANCE.md",
        "SUPPORT.md",
    )
    for relative in required:
        assert (root / relative).is_file()

    readme = (root / "README.md").read_text(encoding="utf-8")
    architecture = (root / "site" / "architecture.html").read_text(encoding="utf-8")
    for name in ("system-architecture", "aws-reference-architecture"):
        assert f"site/assets/{name}.png" in readme
        assert f"assets/{name}.drawio" in architecture
        assert f"assets/{name}.png" in architecture

    pages = (root / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert 'UV_PYTHON: "3.12"' in pages
    assert "uv sync --python \"3.12\" --locked --extra dev" in pages
    assert "node scripts/test_public_site.mjs" in pages

    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "UV_PYTHON: ${{ matrix.python-version }}" in ci
    assert 'UV_PYTHON: "3.12"' in ci


def test_docker_deployment_uses_uv_lockfile() -> None:
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.12-alpine3.24@sha256:" in dockerfile
    assert "COPY --from=ghcr.io/astral-sh/uv:0.10.7@sha256:" in dockerfile
    assert "RUN apk upgrade --no-cache" in dockerfile
    assert "COPY pyproject.toml uv.lock README.md LICENSE ./" in dockerfile
    assert "uv sync --locked --no-dev --no-editable" in dockerfile
    assert "USER pcp" in dockerfile
    assert '"uv", "run", "--locked", "--no-dev", "--no-sync"' in dockerfile
    assert "pip install" not in dockerfile

    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "${PCP_BIND_ADDRESS:-127.0.0.1}:${PCP_PORT:-8102}:8102" in compose
