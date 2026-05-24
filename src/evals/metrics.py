"""
Ranking and classification metrics for the eval harness.

Thin wrappers over sklearn plus hand-rolled top-k metrics. Kept separate from
harness.py so scorers and downstream code can import metrics without pulling
in DB/CLI dependencies.
"""

import numpy as np
from sklearn.metrics import roc_auc_score

def auc(y_true: list[int], y_score: list[float]) -> float:
    """
    Area under ROC curve (AUC). Requires both positive and negative labels.
    
    Raises ValueError if all labels are the same class (cannot compute AUC
    without both positive and negative examples).
    
    Args:
        y_true: binary labels (0 or 1)
        y_score: predicted scores (typically 0.0-1.0)
    
    Returns:
        AUC score (0.0-1.0, where 0.5 = random, 1.0 = perfect)
    """
   
    if len(set(y_true)) == 1:
        raise ValueError("AUC requires both positive (1) and negative (0) labels. Only one class present.")

    return float(roc_auc_score(y_true, y_score))

def precision_at_k(y_true: list[int], y_score: list[float], k: int) -> float:
    """
    Precision@k — fraction of true positives in top-k ranked items.
    
    Measures: "Of the top-k items I retrieved, how many are actually positive?"
    Useful for ranking/retrieval: high precision@k = good ranking quality.
    
    Args:
        y_true: binary labels
        y_score: predicted scores (ranked descending)
        k: cutoff position
    
    Returns:
        Precision@k (0.0-1.0). Clamped to min(k, len(y_true)) if k > list length.
    """
    k = min(k, len(y_true))
    ranked = sorted(zip(y_score, y_true), key=lambda x:x[0], reverse=True)
    top_k_labels = [label for _, label in ranked[:k]]
    return sum(top_k_labels) / k if k > 0 else 0.0

def mrr(y_true: list[int], y_score: list[float]) -> float:
    """
    Mean reciprocal rank (MRR) — rank of the first relevant item.
    
    Measures: "How far down the ranking before I find the first positive?"
    MRR=1.0 if first item is positive; MRR=0.5 if second, etc.
    
    Args:
        y_true: binary labels
        y_score: predicted scores (ranked descending)
    
    Returns:
        1.0 / (rank of first positive). Returns 0.0 if no positive label present.
    """
    ranked = sorted(zip(y_score, y_true), key=lambda x:x[0], reverse=True)
    for rank, (_, label) in enumerate(ranked, start=1):
        if label == 1:
            return 1.0 / rank
    return 0.0

def hit_at_k(y_true: list[int], y_score: list[float], k: int) -> int:
    """
    Hit@k — binary indicator: 1 if any positive in top-k, else 0.
    
    Measures: "Did I find at least one relevant item in my top-k retrieval?"
    Useful for downstream binary tasks (recall-oriented).
    
    Args:
        y_true: binary labels
        y_score: predicted scores (ranked descending)
        k: cutoff position
    
    Returns:
        1 if ≥1 positive label in top-k, else 0
    """
    ranked = sorted(zip(y_score, y_true), key=lambda x:x[0], reverse=True)
    top_k_labels = [label for _, label in ranked[:k]]
    return 1 if any(top_k_labels) else 0