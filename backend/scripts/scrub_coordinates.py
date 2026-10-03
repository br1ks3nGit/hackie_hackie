"""Remove coordinate keys from every GPS sample in stored chunk files.

Dry run by default; pass --apply to rewrite files. Idempotent. Logs counts only.
Usage: uv run python scripts/scrub_coordinates.py [--data-dir DIR] [--apply]
"""

import argparse
import gzip
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.privacy import strip_coordinates

logger = logging.getLogger("scrub_coordinates")


class MalformedChunk(ValueError):
    """Chunk JSON does not have the expected shape."""


SKIP_ERRORS = (
    gzip.BadGzipFile,
    EOFError,
    json.JSONDecodeError,
    UnicodeDecodeError,
    OSError,
    MalformedChunk,
)


def _rewrite(path: Path, chunk: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.open(raw, "wt", encoding="utf-8") as f:
                json.dump(chunk, f)
            raw.flush()
            os.fsync(raw.fileno())
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def scrub_file(path: Path, apply: bool) -> int:
    """Return the number of GPS samples that contain coordinates; rewrite the file if apply."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        chunk = json.load(f)
    if not isinstance(chunk, dict):
        raise MalformedChunk("root is not an object")
    key = "speed_samples" if "speed_samples" in chunk else "gps"  # "gps" = pre-rename files
    gps = chunk.get(key, [])
    if not isinstance(gps, list) or not all(isinstance(s, dict) for s in gps):
        raise MalformedChunk(f"{key} is not a list of objects")
    cleaned = [strip_coordinates(s) for s in gps]
    changed = sum(1 for old, new in zip(gps, cleaned, strict=True) if len(old) != len(new))
    if changed and apply:
        chunk[key] = cleaned
        _rewrite(path, chunk)
    return changed


def scrub_dir(data_dir: Path, apply: bool) -> tuple[int, int, int, int]:
    """Return (files scanned, files changed, samples changed, files skipped)."""
    scanned = files_changed = samples_changed = skipped = 0
    for path in sorted(data_dir.rglob("*.json.gz")):
        scanned += 1
        rel = path.relative_to(data_dir)
        if path.is_symlink():
            logger.warning("Skipped symlink: %s", rel)
            skipped += 1
            continue
        try:
            n = scrub_file(path, apply)
        except SKIP_ERRORS as exc:
            logger.warning("Skipped %s: %s", rel, type(exc).__name__)
            skipped += 1
            continue
        if n:
            files_changed += 1
            samples_changed += n
    return scanned, files_changed, samples_changed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=None, help="chunk root (default: DATA_DIR setting)")
    parser.add_argument("--apply", action="store_true", help="rewrite files (default: dry run)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    data_dir = Path(args.data_dir or get_settings().data_dir)
    if not data_dir.is_dir():
        if args.data_dir:
            logger.error("Data dir not found: %s", data_dir)
            return 2
        logger.info("Data dir not found: %s (nothing to do)", data_dir)
        return 0
    scanned, files_changed, samples, skipped = scrub_dir(data_dir, args.apply)
    verb = "changed" if args.apply else "would change"
    logger.info(
        "%s: scanned %d files; %s %d files, %d GPS samples; skipped %d",
        "APPLY" if args.apply else "DRY RUN",
        scanned,
        verb,
        files_changed,
        samples,
        skipped,
    )
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
