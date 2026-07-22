"""Load and expose the render routing/dialect rules from config/render_rules.yaml.

This module is the single seam between the on-disk render-rules YAML and the
Python render layer (writer, adapter, executor). Everything downstream
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
    shared across the writer/adapter/executor for a render pass.
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

    def still_dialect(self) -> dict:
        """Return the still/image-prompt dialect block.

        The opening still is an IMAGE-model prompt, not a video-model one, so it
        obeys a separate set of rules (directive-stack order, camera-kit,
        authentic-imperfection, composition traps) held under the top-level
        ``still_dialect`` key — distinct from any video model's ``dialect`` block.
        Returns the mapping of named still-rule keys to their rule strings.
        """
        return self.data["still_dialect"]

    def global_constraints(self, kind: str, style: str) -> list[str]:
        """Return the constraint strings that apply to a given prompt ``kind``.

        The ``global_constraints`` block groups constraints under named buckets
        (``always_append``, ``stability``, ``style_consistency``,
        ``audio_cleanliness``, ...). Each bucket is a mapping of
        ``{kinds: [...], rules: [...]}``, where ``kinds`` declares which prompt
        types the bucket applies to (``still``, ``motion``, or both) and
        ``rules`` is the list of constraint strings.

        A bucket is included only if ``kind`` is in its ``kinds`` list — so
        still prompts pick up ``style_consistency`` while motion prompts pick up
        ``audio_cleanliness``, and neither leaks into the other (the i2v rule:
        a motion prompt must not restate the still's look). Any new bucket added
        to the YAML is scoped automatically by its own ``kinds`` declaration.

        The literal ``[STYLE]`` placeholder in any rule string is replaced with
        ``style`` (the shot's concrete style/mood anchor) before the rule is
        returned. Motion call-sites that carry no style language pass
        ``style=""``, leaving any ``[STYLE]`` token to collapse to empty.
        """

        output = []
        for bucket in self.data["global_constraints"].values():
            if kind not in bucket["kinds"]:
                continue

            for rule in bucket["rules"]:
                output.append(rule.replace("[STYLE]", style))

        return output

    def pov_grammar(self) -> dict:
        """Return the ``pov_grammar`` block (ticket 01, POV pipeline).

        Holds the fixed POV skeleton clauses (camera-as-eyes, unseen
        protagonist, anti-drift constraint, constraints block — hands
        visibility is deliberately NOT a clause; it lives in
        ``protagonist_detail_craft`` as a script-stage authoring rule), the
        kill list (dead intensifiers, bare "cinematic", glow/glimmer), the
        per-duration beat budget, the dialogue placement rules, the audio
        rule, and the world-prose craft rules. Every leaf entry carries its
        own ``evidence`` field (probe artifact, corpus citation, or an
        explicit ``candidate`` marker) — this accessor is a plain
        passthrough, the evidence trail lives in the YAML itself, not here.

        The POV prompt compiler (``src/generation/pov/compiler.py``) is the
        sole reader: it composes the fixed clauses verbatim and scrubs the
        kill list from LLM-authored script prose so a proven rule can never
        drift with LLM phrasing (PRD user story 13/14).
        """
        return self.data["pov_grammar"]

    def pov_verdict(self) -> dict:
        """Return the ``pov_verdict`` block (slice ③, .scratch/pov-slice3/PRD.md).

        Holds the verdict flow's defect taxonomy (every countable watch-time
        failure class with its honest guard status — ``code_check`` /
        ``prompt_rule`` / ``watch_only`` — applicability, default
        objective-vs-taste tag, and evidence trail) and the spending brakes
        (``per_story_credit_cap``, ``max_failed_retakes``) plus the
        ``final_resolution`` the probe gate releases. Like ``pov_grammar``,
        this is a plain passthrough — the evidence trail lives in the YAML.

        ``src/generation/pov/verdict.py`` is the sole reader: it validates
        logged defect slugs against the taxonomy, derives the prediction
        block from guarded entries, and enforces the brakes.

        Raises:
            KeyError: if the YAML has no ``pov_verdict`` block.
        """
        return self.data["pov_verdict"]

    def retake_ladder(self) -> str:
        """Return the ``scene_lane.retake_ladder`` wording (480p -> 720p -> 1080p).

        A single sentence documenting the mandatory sanity-then-quality-then-
        finals render sequence (D6). The POV render sheet
        (``src/generation/pov/render_sheet.py``, POV pipeline ticket 03) is
        the current reader: it states this verbatim as the sheet's MANDATORY
        render-ladder wording (PRD user story 16) rather than re-authoring
        the sequence in its own words, so the two can never drift apart.

        Raises:
            KeyError: if the YAML has no ``scene_lane.retake_ladder`` entry.
        """
        return self.data["scene_lane"]["retake_ladder"]

    def scene_model(self) -> str:
        """Return the scene lane's model cli_id from the ``scene_lane`` block.

        The motion-native lane (spec 2026-07-06) renders every package as ONE
        generation on a single model; ``scene_lane.model`` in the YAML is the
        only place that model is named (D7 — a Seedance 2.5 swap is a config
        edit, never a code edit). The writer stamps this id on every ShotSpec;
        the executor submits the scene job against it.

        Raises:
            KeyError: if the YAML has no ``scene_lane.model`` entry.
        """
        return self.data["scene_lane"]["model"]

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

    def max_shots(self, cli_id: str) -> int:
        """Return the maximum internal shots one generation supports for a model.

        Convenience accessor for the ``ratings.max_shots`` value of a model's
        config block — the per-generation shot cap the router uses when sizing
        consistency groups (a Kling group must not exceed the model's own
        multi-shot limit). Reading it from the YAML rather than hardcoding keeps
        model swaps (e.g. a future Seedance 2.5) config-only.

        As with ``max_seconds``, an unknown cli_id — or a model with no
        ``ratings.max_shots`` entry (single-shot-only models) — is treated as a
        programming error and surfaces loudly rather than returning a default.

        Raises:
            KeyError: if ``cli_id`` is not a model defined in the YAML, or that
                model has no ``ratings.max_shots`` entry.
        """
        return self.data["models"][cli_id]["ratings"]["max_shots"]

    def emits_audio(self, cli_id: str) -> bool:
        """Return whether a model generates its own native audio track.

        Reads the ``emits_audio`` flag off a model's config block, defaulting to
        ``False`` when the flag is absent. Unlike ``model``/``max_seconds``, this
        does NOT treat an unknown cli_id as a programming error: the still model
        (``nano_banana_2``) has no entry in the video-models block at all, and a
        still never emits audio, so a missing model resolves to ``False`` rather
        than raising. The executor (Task 6) uses this to warn when a model that
        should carry audio renders a mute clip.
        """
        return self.data["models"].get(cli_id, {}).get("emits_audio", False)