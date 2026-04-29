import numpy as np
from sklearn.metrics import roc_auc_score

def auc(y_true: list[int], y_score: list[float]) -> float:
    """Area under ROC curve. Raises ValueError if only one class present."""
    return float(roc_auc_score(y_true, y_score))

def precision_at_k(y_true: list[int], y_score: list[float], k: int) -> float:
    """Fraction of true positives in top-k ranked items """
    