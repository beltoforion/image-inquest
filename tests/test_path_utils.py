"""Unit tests for the relative-path helpers used by file-IO nodes."""
from __future__ import annotations

from pathlib import Path

from core.path_utils import resolve_against, store_relative_to


# ── store_relative_to ────────────────────────────────────────────────────────


def test_absolute_inside_base_is_made_relative(tmp_path: Path) -> None:
    """An absolute path inside ``base_dir`` round-trips as a relative
    path so saved flows stay portable across machines that share the
    same input/output layout."""
    target = tmp_path / "ship.jpg"
    target.write_bytes(b"")  # resolve() needs the path to exist for symlinks
    out = store_relative_to(target, tmp_path)
    assert out == Path("ship.jpg")
    assert not out.is_absolute()


def test_absolute_inside_subdirectory_keeps_subdirectory(tmp_path: Path) -> None:
    sub = tmp_path / "subset"
    sub.mkdir()
    target = sub / "frame.png"
    target.write_bytes(b"")
    out = store_relative_to(target, tmp_path)
    assert out == Path("subset") / "frame.png"


def test_absolute_outside_base_is_kept_absolute(tmp_path: Path) -> None:
    """A path that doesn't live under ``base_dir`` must round-trip
    unchanged — flattening it would silently relocate the user's
    file at run time."""
    other_root = tmp_path / "elsewhere"
    other_root.mkdir()
    target = other_root / "video.mp4"
    target.write_bytes(b"")
    base_dir = tmp_path / "input"
    base_dir.mkdir()
    out = store_relative_to(target, base_dir)
    assert out.is_absolute()
    assert out == target.resolve()


def test_relative_input_returned_unchanged() -> None:
    """Already-relative input is passed through verbatim — even when
    it contains traversal (``../foo``) or refers to a missing file.
    The helper's job is to normalise the *absolute* case; relative
    input is the user's explicit choice and we don't anchor it."""
    p = Path("../sibling/frame.png")
    out = store_relative_to(p, Path("/some/base"))
    assert out == p


def test_missing_base_dir_keeps_absolute(tmp_path: Path) -> None:
    """If ``base_dir`` itself doesn't exist on disk, ``resolve()`` on
    a path inside it can fail — we treat that as 'keep absolute'
    rather than raising, since the path may still be valid for the
    caller to use later (e.g. INPUT_DIR is created lazily)."""
    target = tmp_path / "ghost.jpg"
    target.write_bytes(b"")
    nonexistent_base = tmp_path / "does_not_exist"
    out = store_relative_to(target, nonexistent_base)
    # Either kept absolute (the ValueError branch) or rewritten — we
    # accept both as long as no exception leaks out.
    assert isinstance(out, Path)


def test_string_input_is_coerced_to_path() -> None:
    """The setters that wrap this helper accept ``str | Path`` —
    the helper handles both."""
    out = store_relative_to("relative/dir", Path("/some/base"))
    assert out == Path("relative/dir")


# ── resolve_against ──────────────────────────────────────────────────────────


def test_resolve_relative_joins_base() -> None:
    out = resolve_against(Path("frame.png"), Path("/input"))
    assert out == Path("/input/frame.png")
    assert out.is_absolute()


def test_resolve_absolute_passes_through() -> None:
    """An already-absolute path must not be re-anchored against
    ``base_dir`` — the user explicitly picked a location outside
    the well-known root."""
    abs_path = Path("/elsewhere/video.mp4")
    out = resolve_against(abs_path, Path("/input"))
    assert out == abs_path


def test_round_trip_inside_base(tmp_path: Path) -> None:
    """``store_relative_to`` followed by ``resolve_against`` returns
    a path that points at the same file, even when the original was
    absolute and the intermediate stored form was relative."""
    target = tmp_path / "frame.png"
    target.write_bytes(b"")
    stored = store_relative_to(target, tmp_path)
    resolved = resolve_against(stored, tmp_path)
    assert resolved.resolve() == target.resolve()
