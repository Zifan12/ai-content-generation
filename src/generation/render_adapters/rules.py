"""Load and expose the render routing/dialect rules from config/render_rules.yaml.

This module is the single seam between the on-disk render-rules YAML and the
Python render layer (router, prompt builders, adapter). Everything downstream
reads rules through a RenderRules instance rather than re-parsing the YAML, so
the file stays the one source of truth (no rule is ever hardcoded in code).
"""

from pathlib import Path

import yaml

# config/render_rules.yaml lives at the repo root; anchor to this file rather
# than the process CWD so RenderRules() loads correctly from any entry point
# (tests, scripts, notebooks, FastAPI startup). render_adapters -> generation
# -> src -> repo root is four parents up.
_RULES_PATH = Path(__file__).resolve().parents[3] / "config" / "render_rules.yaml"


class RenderRules:
    """A read-once, in-memory view over config/render_rules.yaml.

    Construction loads and parses the YAML; the resulting dict is held on
    ``self.data`` and exposed through typed accessor methods (``route``,
    ``model``, ``global_constraints``). One instance is meant to be built and
    shared across the router and builders for a render pass.
    """

    def __init__(self):
        """Load config/render_rules.yaml into ``self.data``.

        Opens the rules file at ``_RULES_PATH`` (anchored to this module's
        location, not the process working directory) and parses it with
        ``yaml.safe_load``. The parsed mapping (top-level keys ``models``,
        ``routing``, ``global_constraints``, etc.) is stored on ``self.data``
        for the accessor methods to read.

        Raises:
            FileNotFoundError: if config/render_rules.yaml is missing.
            yaml.YAMLError: if the file is not valid YAML.
        """
        with open(_RULES_PATH, encoding="utf-8") as f:
            self.data = yaml.safe_load(f)

    def route(self, tag: str) -> list[str]:
        """Return the ranked model cli_ids for a motion routing tag.

        Looks the tag up in the ``routing`` block and returns its ranked list
        of model cli_ids (best-first). An unknown tag is a normal case — the
        router may produce a tag with no explicit entry — so this falls back to
        the ``routing.default`` list rather than raising. The default is read
        from the YAML (not hardcoded here) so it stays in one place.
        """
        return self.data["routing"].get(tag, self.data["routing"]["default"])

    def model(self, cli_id: str) -> dict:
        """Return the full config block for a model, keyed by its cli_id.

        The returned dict includes the model's ``dialect`` and ``ratings``
        sub-blocks (e.g. ``model("veo3_1")["ratings"]["max_seconds"]``).

        Unlike ``route``, an unknown cli_id is treated as a programming error
        (only ids drawn from the YAML should ever be passed here), so this
        indexes directly and lets a missing key raise loudly at the source.

        Raises:
            KeyError: if ``cli_id`` is not a model defined in the YAML.
        """
        return self.data["models"][cli_id]

    def global_constraints(self) -> list[str]:
        """Return every always-append constraint string as one flat list.

        The ``global_constraints`` block groups constraints under sub-keys
        (``always_append``, ``stability``, ``style_consistency``, ...), each a
        list of strings. This flattens across *all* of those sub-lists by
        iterating ``.values()`` — so a new constraint category added to the
        YAML is picked up automatically and nothing is silently dropped.
        """
        return [item for bucket in self.data["global_constraints"].values() for item in bucket]

    def max_seconds(self, cli_id: str) -> int:
        """Return the maximum single-clip duration (seconds) for a model.

        Convenience accessor for the ``ratings.max_seconds`` value of a model's
        config block — the per-shot duration cap the adapter uses to keep a
        motion job within what the chosen model can render in one take.

        As with ``model``, an unknown cli_id is treated as a programming error
        and surfaces loudly rather than returning a default.

        Raises:
            KeyError: if ``cli_id`` is not a model defined in the YAML, or that
                model has no ``ratings.max_seconds`` entry.
        """
        return self.data["models"][cli_id]["ratings"]["max_seconds"]