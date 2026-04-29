import numpy as np
from sklearn.metrics import roc_auc_score

def auc(y_true: list[int], y_score: list[float]) -> float:
    """Area under ROC curve. Raises ValueError if only one class present."""
   
    if len(set(y_true)) == 1:
        raise ValueError

    return float(roc_auc_score(y_true, y_score))

def precision_at_k(y_true: list[int], y_score: list[float], k: int) -> float:
    """Fraction of true positives in top-k ranked items """
    k = min(k, len(y_true))
    ranked = sorted(zip(y_score, y_true), key=lambda x:x[0], reverse=True)
    top_k_labels = [label for _, label in ranked[:k]]
    return sum(top_k_labels) / k

def mrr(y_true: list[int], y_score: list[float]) -> float:
    """Mean reciprocal rank of the first true positive."""
    ranked = sorted(zip(y_score, y_true), key=lambda x:x[0], reverse=True)
    for rank, (_, label) in enumerate(ranked, start=1):
        if label == 1:
            return 1.0 / rank
    return 0.0

def hit_at_k(y_true: list[int], y_score: list[float], k: int) -> int:
    """1 if any true positive in top-k, else 0."""
    ranked = sorted(zip(y_score, y_true), key=lambda x:x[0], reverse=True)
    top_k_labels = [label for _, label in ranked[:k]]
    return 1 if any(top_k_labels) else 0