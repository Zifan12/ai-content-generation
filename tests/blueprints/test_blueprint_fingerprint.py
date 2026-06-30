from src.blueprints.extractor import compute_prompt_fingerprint

SYSTEM = "You are an expert analyst."
ENVELOPE = "Caption: surreal void. Duration: 15s."
MODEL = "claude-sonnet-5"
PARAMS = {"max_tokens": 2048, "temperature": 0}


def test_same_inputs_same_hash():
    """Determinism: identical inputs always produce the same fingerprint."""
    a = compute_prompt_fingerprint(SYSTEM, ENVELOPE, MODEL, PARAMS)
    b = compute_prompt_fingerprint(SYSTEM, ENVELOPE, MODEL, PARAMS)
    assert a == b


def test_different_system_prompt_different_hash():
    """Changing system prompt invalidates the fingerprint."""
    a = compute_prompt_fingerprint(SYSTEM, ENVELOPE, MODEL, PARAMS)
    b = compute_prompt_fingerprint(SYSTEM + " extra.", ENVELOPE, MODEL, PARAMS)
    assert a != b


def test_different_envelope_different_hash():
    """Changing envelope (per-item context) invalidates the fingerprint."""
    a = compute_prompt_fingerprint(SYSTEM, ENVELOPE, MODEL, PARAMS)
    b = compute_prompt_fingerprint(SYSTEM, ENVELOPE + " extra.", MODEL, PARAMS)
    assert a != b


def test_different_model_different_hash():
    """Changing model identifier invalidates the fingerprint."""
    a = compute_prompt_fingerprint(SYSTEM, ENVELOPE, MODEL, PARAMS)
    b = compute_prompt_fingerprint(SYSTEM, ENVELOPE, "claude-haiku-4-5", PARAMS)
    assert a != b


def test_sampling_params_key_order_irrelevant():
    """Dict key order in sampling_params does not affect the fingerprint."""
    params_ab = {"max_tokens": 2048, "temperature": 0}
    params_ba = {"temperature": 0, "max_tokens": 2048}
    a = compute_prompt_fingerprint(SYSTEM, ENVELOPE, MODEL, params_ab)
    b = compute_prompt_fingerprint(SYSTEM, ENVELOPE, MODEL, params_ba)
    assert a == b


def test_fingerprint_is_64_char_hex():
    """Output is a valid SHA-256 hex digest — exactly 64 lowercase hex characters."""
    fp = compute_prompt_fingerprint(SYSTEM, ENVELOPE, MODEL, PARAMS)
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)
