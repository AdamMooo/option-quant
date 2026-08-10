from analysis import scorer


def test_smoke_imports_and_scores_contract():
    contract = {
        "type": "C",
        "ivr": 50,
        "ivp": 50,
        "vrp": 0,
        "gamma": 0.01,
        "spread_pct": 1.0,
        "open_interest": 100,
        "dte": 30,
        "price": 100.0,
        "ma20": 99.0,
        "ma50": 98.0,
        "ma200": 95.0,
        "rsi14": 35.0,
        "mom20": 0.01,
        "mom60": 0.01,
        "rs20": 0.01,
        "days_to_earnings": 30,
    }

    score = scorer.score_contract(contract)

    assert isinstance(score, float)
    assert contract["quality_score"] >= 0
    assert contract["direction_score"] >= 0