import gzip
import json
import os
import runpy
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "scrub_coordinates.py"
GPS = {"t": 1, "lat": 1.5, "lon": 2.5, "speed": 3.0, "heading": 4.0, "accuracy": 5.0}


def _write(path: Path, gps: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"seq": 0, "imu": [{"t": 1}], "gps": gps, "car_connected": True}, f)


def _read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _run(monkeypatch: pytest.MonkeyPatch, *args: str, code: int = 0) -> None:
    monkeypatch.setattr(sys, "argv", ["scrub_coordinates.py", *args])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert exc.value.code == code


def test_scrub_dry_run_apply_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    path = tmp_path / "trip1" / "0.json.gz"
    _write(path, [dict(GPS), dict(GPS, t=2)])
    _write(tmp_path / "trip1" / "1.json.gz", [{"t": 1, "speed": 1.0}])
    before = path.read_bytes()

    _run(monkeypatch, "--data-dir", str(tmp_path))
    err = caplog.text
    caplog.clear()
    assert "DRY RUN" in err and "would change 1 files, 2 GPS samples" in err
    assert path.read_bytes() == before

    _run(monkeypatch, "--data-dir", str(tmp_path), "--apply")
    assert "changed 1 files, 2 GPS samples" in caplog.text
    caplog.clear()
    chunk = _read(path)
    assert chunk["imu"] == [{"t": 1}]
    assert chunk["gps"][0] == {"t": 1, "speed": 3.0, "heading": 4.0, "accuracy": 5.0}
    assert not list(tmp_path.rglob("*.tmp"))

    _run(monkeypatch, "--data-dir", str(tmp_path), "--apply")
    assert "changed 0 files, 0 GPS samples" in caplog.text


def test_bad_files_skipped_and_others_processed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    good = tmp_path / "t" / "0.json.gz"
    _write(good, [dict(GPS)])
    (tmp_path / "t" / "1.json.gz").write_bytes(b"not gzip at all")
    with gzip.open(tmp_path / "t" / "2.json.gz", "wt", encoding="utf-8") as f:
        json.dump([1, 2], f)
    with gzip.open(tmp_path / "t" / "3.json.gz", "wt", encoding="utf-8") as f:
        json.dump({"gps": [1]}, f)

    _run(monkeypatch, "--data-dir", str(tmp_path), "--apply", code=1)
    assert "skipped 3" in caplog.text
    assert "1.json.gz: BadGzipFile" in caplog.text
    assert "not gzip" not in caplog.text
    assert "lat" not in _read(good)["gps"][0]


def test_chunk_without_gps_key_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    path = tmp_path / "0.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"seq": 0, "imu": []}, f)
    before = path.read_bytes()
    _run(monkeypatch, "--data-dir", str(tmp_path), "--apply")
    assert path.read_bytes() == before
    assert "skipped 0" in caplog.text


def test_symlink_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = tmp_path / "outside" / "0.json.gz"
    _write(real, [dict(GPS)])
    root = tmp_path / "root"
    root.mkdir()
    link = root / "link.json.gz"
    link.symlink_to(real)
    _run(monkeypatch, "--data-dir", str(root), "--apply", code=1)
    assert link.is_symlink()
    assert "lat" in _read(real)["gps"][0]


def test_missing_explicit_data_dir_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, "--data-dir", str(tmp_path / "nope"), code=2)


def test_file_mode_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "0.json.gz"
    _write(path, [dict(GPS)])
    path.chmod(0o644)
    _run(monkeypatch, "--data-dir", str(tmp_path), "--apply")
    assert os.stat(path).st_mode & 0o777 == 0o644
    assert "lat" not in _read(path)["gps"][0]
