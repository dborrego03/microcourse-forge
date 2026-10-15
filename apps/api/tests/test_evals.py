from forge.evals import check, first_hit, generation_metrics, normalize, retrieval_metrics


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


def test_generation_metrics_count_failures_and_skip_cached_latency():
    rubric = {name: 4 for name in ("alignment", "accuracy", "clarity", "examples", "assessment", "structure")}
    ready = {"status": "ready", "retries": 0, "cached": False, "cost_usd": 0.01, "latency_ms": 20000,
             "claims": 10, "supported": 9, "relevance": 5, "rubric": rubric}  # fmt: skip
    rows = [
        ready,
        {**ready, "retries": 1, "cached": True, "latency_ms": 5, "supported": 7},
        {"status": "failed"},
    ]

    metrics = generation_metrics(rows)

    assert metrics["valid_rate"] == round(2 / 3, 3)
    assert metrics["valid_first_try_rate"] == round(1 / 3, 3)
    assert metrics["faithfulness"] == 0.8  # 16 of 20 claims
    assert metrics["rubric_mean"] == 4
    assert metrics["lesson_latency_p50_ms"] == 20000  # the cached lesson is left out
    assert metrics["fresh_lessons"] == 1
