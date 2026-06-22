import pytest
from src.evals.metrics import auc, precision_at_k, mrr, hit_at_k


# --- auc ---

def test_auc_perfect():
    y_true = [1, 1, 0, 0]
    y_score = [0.9, 0.8, 0.2, 0.1]
    assert auc(y_true, y_score) == pytest.approx(1.0)


def test_auc_random():
    y_true = [1, 0, 1, 0]
    y_score = [0.6, 0.4, 0.4, 0.6]
    result = auc(y_true, y_score)
    assert 0.0 <= result <= 1.0


def test_auc_all_same_label_raises():
    with pytest.raises(ValueError):
        auc([1, 1, 1], [0.9, 0.8, 0.7])


# --- precision_at_k ---

def test_precision_at_k_all_correct():
    y_true = [1, 1, 1, 0, 0]
    y_score = [0.9, 0.8, 0.7, 0.3, 0.1]
    assert precision_at_k(y_true, y_score, k=3) == pytest.approx(1.0)


def test_precision_at_k_none_correct():
    y_true = [0, 0, 0, 1, 1]
    y_score = [0.9, 0.8, 0.7, 0.3, 0.1]
    assert precision_at_k(y_true, y_score, k=3) == pytest.approx(0.0)


def test_precision_at_k_partial():
    y_true = [1, 0, 1, 0, 0]
    y_score = [0.9, 0.8, 0.7, 0.3, 0.1]
    assert precision_at_k(y_true, y_score, k=3) == pytest.approx(2 / 3)


def test_precision_at_k_larger_than_list():
    y_true = [1, 0]
    y_score = [0.9, 0.1]
    assert precision_at_k(y_true, y_score, k=10) == pytest.approx(0.5)


# --- mrr ---

def test_mrr_first_hit_rank_1():
    y_true = [1, 0, 0]
    y_score = [0.9, 0.5, 0.1]
    assert mrr(y_true, y_score) == pytest.approx(1.0)


def test_mrr_first_hit_rank_2():
    y_true = [0, 1, 0]
    y_score = [0.9, 0.8, 0.1]
    assert mrr(y_true, y_score) == pytest.approx(0.5)


def test_mrr_no_hits():
    y_true = [0, 0, 0]
    y_score = [0.9, 0.5, 0.1]
    assert mrr(y_true, y_score) == pytest.approx(0.0)


# --- hit_at_k ---

def test_hit_at_k_found():
    y_true = [0, 0, 1]
    y_score = [0.9, 0.8, 0.7]
    assert hit_at_k(y_true, y_score, k=3) == 1


def test_hit_at_k_not_found():
    y_true = [0, 0, 1]
    y_score = [0.9, 0.8, 0.7]
    assert hit_at_k(y_true, y_score, k=2) == 0


def test_hit_at_k_found_at_exactly_k():
    y_true = [0, 1, 0]
    y_score = [0.9, 0.8, 0.7]
    assert hit_at_k(y_true, y_score, k=2) == 1
