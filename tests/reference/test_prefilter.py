"""
Tests for src/reference/frame_harvester.py prefilter — all offline, using
synthetic PNGs generated with PIL/numpy into tmp_path (no downloads, no ffmpeg).

Each test tunes only the thresholds relevant to the gate under test (e.g.
sharpness_min=0 to neutralize the blur gate when isolating the dark gate), so a
failure points at one filter rather than an interaction.
"""

from pathlib import Path

import numpy as np
from PIL import Image

from src.reference.frame_harvester import prefilter


def _save(arr: np.ndarray, path: Path) -> Path:
    """Save a uint8 array (HxW grayscale or HxWx3 RGB) as a PNG."""
    Image.fromarray(arr).save(path)
    return path


def _checkerboard(path: Path, *, size: int = 64, tile: int = 8, a: int = 0, b: int = 255) -> Path:
    """High-edge-content image: sharp (high Laplacian variance)."""
    arr = np.full((size, size), a, dtype=np.uint8)
    for y in range(size):
        for x in range(size):
            if ((x // tile) + (y // tile)) % 2 == 0:
                arr[y, x] = b
    return _save(arr, path)


def _solid(path: Path, *, size: int = 64, value: int = 127) -> Path:
    """Flat image: zero edges (Laplacian variance 0), mean == value."""
    return _save(np.full((size, size), value, dtype=np.uint8), path)


def _square(path: Path, *, idx: int, size: int = 64) -> Path:
    """Black background with one large white block in a distinct grid cell —
    the spatial displacement gives each idx a perceptually distinct pHash."""
    arr = np.zeros((size, size), dtype=np.uint8)
    cells = 4
    cell = size // cells
    row, col = divmod(idx, cells)
    y0, x0 = row * cell, col * cell
    arr[y0 : y0 + cell, x0 : x0 + cell] = 255
    return _save(arr, path)


def test_empty_input_returns_empty_list():
    assert prefilter([], sharpness_min=100, phash_distance_min=6, luminance_min=40, max_out=8) == []


def test_blurry_solid_frame_rejected(tmp_path):
    # Flat grey: bright enough (mean 127) but zero edges -> fails the blur gate.
    flat = _solid(tmp_path / "flat.png", value=127)
    result = prefilter(
        [flat], sharpness_min=100, phash_distance_min=6, luminance_min=0, max_out=8
    )
    assert result == []


def test_sharp_bright_frame_passes(tmp_path):
    board = _checkerboard(tmp_path / "board.png")
    result = prefilter(
        [board], sharpness_min=100, phash_distance_min=6, luminance_min=0, max_out=8
    )
    assert len(result) == 1
    assert result[0].path == str(board)
    assert result[0].sharpness > 100
    assert result[0].verdict is None  # judge fills this later


def test_dark_frame_rejected_independent_of_sharpness(tmp_path):
    # sharpness_min=0 neutralizes the blur gate; a dark flat frame (mean 10)
    # must still be rejected by the luminance gate.
    dark = _solid(tmp_path / "dark.png", value=10)
    result = prefilter(
        [dark], sharpness_min=0, phash_distance_min=6, luminance_min=40, max_out=8
    )
    assert result == []


def test_near_duplicate_collapses_to_one(tmp_path):
    board = _checkerboard(tmp_path / "board.png")
    # Re-saved copy of the same image -> identical pHash (distance 0 < 6).
    copy = _checkerboard(tmp_path / "board_copy.png")
    result = prefilter(
        [board, copy], sharpness_min=100, phash_distance_min=6, luminance_min=0, max_out=8
    )
    assert len(result) == 1


def test_cap_counts_distinct_shots(tmp_path):
    # Six perceptually-distinct sharp frames, cap at 3 distinct shots.
    frames = [_square(tmp_path / f"sq_{i}.png", idx=i) for i in range(6)]
    result = prefilter(
        frames, sharpness_min=0, phash_distance_min=6, luminance_min=0, max_out=3
    )
    assert len(result) == 3


def test_output_sorted_sharpest_first(tmp_path):
    sharp = _checkerboard(tmp_path / "sharp.png", tile=4)   # finer tiles -> more edges
    softer = _checkerboard(tmp_path / "softer.png", tile=32)  # coarser -> fewer edges
    result = prefilter(
        [softer, sharp], sharpness_min=0, phash_distance_min=6, luminance_min=0, max_out=8
    )
    assert [fs.path for fs in result] == [str(sharp), str(softer)]
    assert result[0].sharpness >= result[1].sharpness
