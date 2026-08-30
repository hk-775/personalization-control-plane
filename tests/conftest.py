from __future__ import annotations

import os
import tempfile
from copy import deepcopy
from pathlib import Path

os.environ.setdefault(
    "PCP_DB_PATH",
    str(Path(tempfile.gettempdir()) / "pcp-pytest-import.db"),
)

import pytest
from fastapi.testclient import TestClient

from personalization_control_plane.app import create_app
from personalization_control_plane.seed import DEMO_CANDIDATES


@pytest.fixture
def app(tmp_path: Path):
    return create_app(tmp_path / "control-plane.db")


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def commerce_rank_payload() -> dict:
    return {
        "request_id": "req-test-commerce-001",
        "subject_id": "subject-commerce-001",
        "domain": "commerce",
        "purpose": "help people find useful products they are likely to value",
        "consent": True,
        "cohort_id": "cohort-commerce-returning",
        "candidates": deepcopy(DEMO_CANDIDATES["commerce"]),
        "limit": 4,
    }
