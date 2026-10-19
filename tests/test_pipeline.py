"""Offline tests for the pipeline logic (no API calls: clients are faked)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from factcheck import annotate, clean, collect, config  # noqa: E402

GROK = config.GROK_AUTHOR_ID


# --- config ---------------------------------------------------------------------------
def test_search_terms_cover_every_keyword_in_both_periods():
    for lang, keywords in config.GROK_REPLY_KEYWORDS.items():
        terms = config.search_terms(lang)
        assert len(terms) == 2 * len(keywords)
        assert terms[0] == f'from:grok "{keywords[0]}" filter:replies since:2025-03-01 until:2025-06-01'
        assert terms[1].endswith("since:2026-02-01 until:2026-05-01")


# --- collect -----------------------------------------------------------------------------
def tweet(id_, reply_to=None, author="u1", text="x" * 80, **extra):
    return {"id": id_, "text": text, "inReplyToId": reply_to, "isReply": reply_to is not None,
            "author": {"id": author, "followers": 10}, **extra}


def test_flatten_keeps_fields_and_author():
    df = collect.flatten([tweet("1", "0", viewCount=5)])
    assert df.loc[0, "author_id"] == "u1"
    assert df.loc[0, "viewCount"] == 5
    assert list(df.columns) == collect.TWEET_FIELDS + list(collect.AUTHOR_FIELDS.values())


def test_build_threads_links_three_levels_and_drops_missing_claims():
    grok = collect.flatten([tweet("g1", "r1", GROK), tweet("g2", "r2", GROK)])
    requests = collect.flatten([tweet("r1", "c1"), tweet("r2", "c_missing")])
    claims = collect.flatten([tweet("c1", text="the claim")])
    out = collect.build_threads(grok, requests, claims)
    assert out["id"].tolist() == ["g1"]
    assert out.loc[0, "df2_id"] == "r1"
    assert out.loc[0, "df3_text"] == "the claim"


def test_actor_inputs():
    step1 = collect.search_input("es")
    assert step1["filter:has_engagement"] is True and step1["lang"] == "es"
    assert step1["searchTerms"] == config.search_terms("es")
    step2 = collect.by_ids_input(["1", "2"], max_items=5)
    assert step2["tweetIDs"] == ["1", "2"] and step2["filter:has_engagement"] is False


# --- clean ---------------------------------------------------------------------------------
def test_cleaning_funnel():
    ok = "a" * 100
    rows = [
        {"id": "1", "text": ok, "df2_text": ok, "df3_text": ok, "df3_author_id": "u"},       # kept
        {"id": "1", "text": ok, "df2_text": ok, "df3_text": ok, "df3_author_id": "u"},       # duplicate
        {"id": "2", "text": ok, "df2_text": ok, "df3_text": ok, "df3_author_id": GROK},      # Grok vs Grok
        {"id": "3", "text": "a" * 2001, "df2_text": ok, "df3_text": ok, "df3_author_id": "u"},  # long reply
        {"id": "4", "text": ok, "df2_text": ok, "df3_text": "https://t.co/x", "df3_author_id": "u"},  # link only
    ]
    df, funnel = clean.clean(pd.DataFrame(rows))
    assert df["id"].tolist() == ["1"]
    assert funnel["rows_after"].iloc[-1] == 1
    assert funnel["removed"].sum() == 4


# --- annotate ------------------------------------------------------------------------------
class FakeModels:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def generate_content(self, **_):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply)


def fake_client(*replies):
    return SimpleNamespace(models=FakeModels(replies))


def test_filter_parses_fenced_json_and_skips_empty_claims():
    client = fake_client('```json\n{"es_validable": "válido"}\n```')
    assert annotate.is_checkable(client, "Spain won the 2010 World Cup") == "válido"
    assert annotate.is_checkable(client, None) == "no_válido"
    assert client.models.calls == 1


def test_judge_retries_then_validates(monkeypatch):
    monkeypatch.setattr(annotate.time, "sleep", lambda _: None)
    client = fake_client(RuntimeError("503"), '{"verdict": "Mostly-Same", "confidence": 1.7, "theme": "Sports"}')
    assert annotate.judge(client, "A", "B") == {"verdict": "mostly_same", "confidence": 1.0, "theme": "sports"}


def test_judge_falls_back_after_max_retries(monkeypatch):
    monkeypatch.setattr(annotate.time, "sleep", lambda _: None)
    client = fake_client(*["not json"] * config.MAX_RETRIES)
    assert annotate.judge(client, "A", "B") == annotate.JUDGE_FALLBACK


@pytest.mark.parametrize("raw, expected", [
    ({"verdict": "disparity", "confidence": "0.333", "theme": "war"}, ("disparity", 0.33, "war")),
    ({"verdict": "??", "confidence": None, "theme": "made-up"}, ("unknown", 0.5, "other")),
])
def test_validate_judgement(raw, expected):
    out = annotate.validate_judgement(raw)
    assert (out["verdict"], out["confidence"], out["theme"]) == expected


def test_run_resumable_continues_from_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(annotate.time, "sleep", lambda _: None)
    df = pd.DataFrame({"id": ["a", "b", "c"], "x": [1, 2, 3]})
    calls = []

    def fn(row):
        calls.append(row["id"])
        if row["id"] == "c" and calls.count("c") == 1:
            raise KeyboardInterrupt  # simulate the session dying mid-batch
        return {"y": row["x"] * 10}

    ckpt = tmp_path / "ckpt.csv"
    with pytest.raises(KeyboardInterrupt):
        annotate.run_resumable(df, fn, ["y"], ckpt, every=1, pause=0)
    out = annotate.run_resumable(df, fn, ["y"], ckpt, every=1, pause=0)
    assert calls == ["a", "b", "c", "c"]  # a and b were not paid for twice
    assert out["y"].tolist() == [10, 20, 30]
