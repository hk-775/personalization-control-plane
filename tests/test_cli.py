from __future__ import annotations

import os
import sys
from pathlib import Path

from personalization_control_plane import cli


def test_cli_starts_seeded_demo_on_configured_port(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    database_path = tmp_path / "demo.db"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pcp-demo",
            "--host",
            "0.0.0.0",
            "--port",
            "8102",
            "--db",
            str(database_path),
            "--log-level",
            "debug",
        ],
    )

    def fake_run(application, **kwargs) -> None:
        captured["application"] = application
        captured.update(kwargs)

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)

    cli.main()

    assert os.environ["PCP_DB_PATH"] == str(database_path)
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8102
    assert captured["log_level"] == "debug"
    assert captured["access_log"] is True
    assert captured["application"] is not None

    output = capsys.readouterr().out
    assert "http://0.0.0.0:8102/dashboard" in output
    assert "http://0.0.0.0:8102/architecture" in output
