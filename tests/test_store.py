import store


def sample_job(job_id="job-1", company="Acme", title="Junior Engineer"):
    return {
        "job_id": job_id, "company": company, "title": title, "location": "London",
        "url": "https://example.com/" + job_id, "description": "Advert text", "source": "test",
    }


def sample_score(score=70, verdict="apply"):
    return {"score": score, "verdict": verdict, "reasons": ["fits"], "red_flags": ["far"], "hard_blockers": []}


def test_empty_when_no_file(tmp_path):
    assert store.load_results(str(tmp_path / "none.json")) == {}


def test_add_and_load_round_trip(tmp_path):
    path = str(tmp_path / "results.json")
    record = store.make_record(sample_job(), sample_score(), store.STATUS_READY, "letter text", "notes")
    store.add_record(record, path)
    loaded = store.load_results(path)
    assert loaded["job-1"]["company"] == "Acme"
    assert loaded["job-1"]["letter"] == "letter text"
    assert loaded["job-1"]["score"] == 70


def test_corrupt_file_gives_empty_results(tmp_path):
    path = tmp_path / "results.json"
    path.write_text("{ not json")
    assert store.load_results(str(path)) == {}


def test_update_record_changes_only_given_fields(tmp_path):
    path = str(tmp_path / "results.json")
    store.add_record(store.make_record(sample_job(), sample_score(), store.STATUS_READY, "old"), path)
    updated = store.update_record("job-1", {"letter": "new"}, path)
    assert updated["letter"] == "new"
    assert updated["company"] == "Acme"
    assert store.update_record("missing", {"letter": "x"}, path) is None


def test_list_records_best_score_first(tmp_path):
    path = str(tmp_path / "results.json")
    store.add_record(store.make_record(sample_job("a"), sample_score(40, "skip"), store.STATUS_SCORED_ONLY), path)
    store.add_record(store.make_record(sample_job("b"), sample_score(80), store.STATUS_READY), path)
    store.add_record(store.make_record(sample_job("c"), sample_score(60, "maybe"), store.STATUS_SCORED_ONLY), path)
    scores = []
    for record in store.list_records(path):
        scores.append(record["score"])
    assert scores == [80, 60, 40]


def test_agreement_with_agent():
    records = [
        {"verdict": "apply", "my_verdict": "apply"},
        {"verdict": "maybe", "my_verdict": "skip"},
        {"verdict": "skip", "my_verdict": ""},
    ]
    assert store.agreement_with_agent(records) == (2, 1)


def test_rebuilt_job_and_score_result():
    record = store.make_record(sample_job(), sample_score(), store.STATUS_READY)
    job = store.job_from_record(record)
    assert job["description"] == "Advert text"
    assert store.score_result_from_record(record)["reasons"] == ["fits"]
