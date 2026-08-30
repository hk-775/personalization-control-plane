from __future__ import annotations

import importlib.util
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
