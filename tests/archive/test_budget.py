from scripts.archive.budget import BudgetTracker


def test_fresh_tracker_not_exhausted(tmp_path):
    bt = BudgetTracker(tmp_path, cap_usd=30.0)
    assert not bt.exhausted()
    assert bt.remaining() == 30.0


def test_charge_accumulates_spend(tmp_path):
    bt = BudgetTracker(tmp_path, cap_usd=30.0)
    bt.charge(1000)  # 1000 items * $0.30/1K = $0.30
    assert round(bt.est_spend_usd, 4) == 0.30
    assert round(bt.remaining(), 4) == 29.70


def test_exhausted_at_cap(tmp_path):
    bt = BudgetTracker(tmp_path, cap_usd=0.30)
    bt.charge(1000)
    assert bt.exhausted()


def test_resume_reloads_prior_spend(tmp_path):
    BudgetTracker(tmp_path, cap_usd=30.0).charge(2000)
    resumed = BudgetTracker(tmp_path, cap_usd=30.0)
    assert resumed.items_returned == 2000
    assert round(resumed.est_spend_usd, 4) == 0.60
