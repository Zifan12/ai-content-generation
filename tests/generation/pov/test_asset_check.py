"""Seam-2 tests for the D2 object role on the POV asset gate (ticket 02).

Character-role behavior is covered at seam 1 (tests/cli/test_pov.py, asset
gate section); these tests pin the OBJECT additions at the pure-function
level: `--object` parsing, the promoted-files-only directory contract
(`candidates/` never counts), object role bounds, and the upload-order
contract extension (characters first, then objects — the imageN numbering
downstream binding sentences rely on).
"""

from pathlib import Path

import pytest

from src.generation.pov.asset_check import (
    DeclaredCharacter,
    POVAssetRequestNeeded,
    check_assets,
    parse_character_args,
    parse_object_args,
)

# Same minimal PNG header as tests/cli/test_pov.py — the gate checks magic bytes.
_PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 13


def _write_refs(refs_root: Path, slug: str, names: list[str]) -> list[Path]:
    d = refs_root / slug
    d.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names:
        p = d / name
        p.write_bytes(_PNG_HEADER)
        paths.append(p)
    return paths


# --- parse_object_args -------------------------------------------------------


def test_object_args_parse_to_object_role_declarations() -> None:
    declared = parse_object_args(["heaven_city", "hell_city"])

    assert declared == [
        DeclaredCharacter(slug="heaven_city", role="object"),
        DeclaredCharacter(slug="hell_city", role="object"),
    ]


def test_object_args_reject_role_suffix_syntax() -> None:
    """Objects have exactly one role — a --character-style :role suffix on
    --object is operator confusion, refused loudly."""
    with pytest.raises(ValueError, match="role"):
        parse_object_args(["heaven_city:in_frame"])


def test_object_args_reject_bad_slug_and_duplicates() -> None:
    with pytest.raises(ValueError, match="slug"):
        parse_object_args(["Heaven City!"])
    with pytest.raises(ValueError, match="more than once"):
        parse_object_args(["hell_city", "hell_city"])


def test_object_slug_colliding_with_a_character_slug_is_rejected() -> None:
    """One slug = one refs/<slug>/ directory — the same slug declared as both
    a character and an object would silently share a library."""
    characters = parse_character_args(["silverhero"])
    with pytest.raises(ValueError, match="more than once"):
        parse_object_args(["silverhero"], taken={c.slug for c in characters})


def test_character_args_still_reject_the_object_role() -> None:
    """`--character x:object` is not a back door — objects come in through
    --object only."""
    with pytest.raises(ValueError, match="unknown role"):
        parse_character_args(["tower:object"])


# --- check_assets: object role ----------------------------------------------


def test_missing_object_dir_halts_with_request_sheet(tmp_path: Path) -> None:
    with pytest.raises(POVAssetRequestNeeded) as exc_info:
        check_assets(parse_object_args(["hell_city"]), tmp_path / "refs")

    sheet = exc_info.value.sheet_text
    assert "hell_city" in sheet
    assert "object" in sheet
    # Element-ref discipline is stated on the sheet: object alone, never the
    # composed target frame (probe-B static-hijack lesson).
    assert "composed" in sheet.lower() or "alone" in sheet.lower()


def test_candidates_subdir_never_counts_as_promoted_refs(tmp_path: Path) -> None:
    """A dir holding ONLY unpicked candidates is the not-yet-promoted state —
    the gate must halt (request/generation), not validate candidates as refs."""
    refs = tmp_path / "refs"
    _write_refs(refs / "hell_city", "candidates", ["c1.png", "c2.png"])

    with pytest.raises(POVAssetRequestNeeded):
        check_assets(parse_object_args(["hell_city"]), refs)


def test_promoted_object_ref_passes_alongside_ignored_candidates(tmp_path: Path) -> None:
    refs = tmp_path / "refs"
    _write_refs(refs, "hell_city", ["keeper.png"])
    _write_refs(refs / "hell_city", "candidates", ["c1.png", "c2.png"])

    resolved = check_assets(parse_object_args(["hell_city"]), refs)

    assert [p.name for r in resolved for p in r.ref_paths] == ["keeper.png"]


def test_object_role_bounds_are_one_to_two(tmp_path: Path) -> None:
    """Element refs carry ONE object's look — probe C used exactly one crop per
    object; a second angle is allowed, a character-style 4-panel sheet is not."""
    refs = tmp_path / "refs"
    _write_refs(refs, "hell_city", ["a.png", "b.png", "c.png"])

    with pytest.raises(ValueError, match="hell_city"):
        check_assets(parse_object_args(["hell_city"]), refs)


def test_upload_order_is_characters_then_objects(tmp_path: Path) -> None:
    """The imageN contract (D2 PRD): characters first (declaration order),
    then objects (declaration order) — regardless of how flags interleave."""
    refs = tmp_path / "refs"
    _write_refs(refs, "hero", ["arm.png", "glove.png"])
    _write_refs(refs, "hell_city", ["hell.png"])
    _write_refs(refs, "heaven_city", ["heaven.png"])

    declared = parse_object_args(["hell_city", "heaven_city"]) + parse_character_args(
        ["hero"]
    )
    resolved = check_assets(declared, refs)

    assert [r.slug for r in resolved] == ["hero", "hell_city", "heaven_city"]
    assert [p.name for r in resolved for p in r.ref_paths] == [
        "arm.png", "glove.png", "hell.png", "heaven.png",
    ]
