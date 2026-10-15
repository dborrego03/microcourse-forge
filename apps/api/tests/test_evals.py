from forge.evals import check, first_hit, normalize, retrieval_metrics


def test_normalize_ignores_curly_quotes_case_and_spacing():
    assert normalize("The  “firefighter\nschema”") == normalize('the "firefighter schema"')


def test_first_hit_returns_the_rank_of_the_first_match():
    results = [{"text": "nothing here"}, {"text": "Pavlov’s dogs salivated"}, {"text": "Pavlov's dogs again"}]
    assert first_hit(results, "pavlov's dogs") == 2
    assert first_hit(results, "Skinner box") is None


def test_retrieval_metrics():
    metrics = retrieval_metrics([1, 2, None, 4])
    assert metrics["hit@1"] == 0.25
    assert metrics["hit@3"] == 0.5
    assert metrics["hit@5"] == 0.75
    assert metrics["mrr@10"] == round((1 + 1 / 2 + 1 / 4) / 4, 3)


def test_check_reports_metrics_below_the_threshold():
    report = {"kind": "retrieval", "config": {"mode": "rerank"}, "metrics": {"hit@5": 0.99, "mrr@10": 0.1}}
    failures = check(report)
    assert len(failures) == 1
    assert failures[0].startswith("mrr@10 = 0.1 is below")
