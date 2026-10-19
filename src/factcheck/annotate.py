"""Step 3 - LLM annotation pipeline (Gemini).

    1. filter     is the claim fact-checkable?                    -> es_validable
    2. reference  independent fact-check with Google Search        -> gemini_factcheck
    3. judge      a different model compares Grok vs. reference    -> comparison_verdict,
                                                                     verdict_confidence,
                                                                     thematic_category

Every step goes through `run_resumable`, which saves a checkpoint every few rows
and skips rows already done. A failed API call or a closed session no longer
means re-running (and paying for) the whole batch.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable

import pandas as pd

from . import config


def make_client(api_key: str | None = None):
    """Gemini client. Reads GEMINI_API_KEY from the environment if no key is passed."""
    from google import genai
    return genai.Client(api_key=api_key) if api_key else genai.Client()


def _text(value, limit: int | None = None) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:limit] if limit else text


def _with_retries(call: Callable[[], object], fallback, retries: int = config.MAX_RETRIES, wait: float = 1.0):
    for attempt in range(1, retries + 1):
        try:
            return call()
        except Exception as exc:  # API errors, malformed JSON...
            print(f"  attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                time.sleep(wait * 2 ** attempt)
    return fallback


def _extract_json(raw: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    return json.loads(match.group(0) if match else clean)


# --- 1. Fact-checkability filter ---------------------------------------------------
def is_checkable(client, claim: str) -> str:
    claim = _text(claim, limit=2000)
    if not claim:
        return "no_válido"

    def call():
        response = client.models.generate_content(
            model=config.MODEL_FILTER, contents=config.VALIDATION_PROMPT.format(claim=claim))
        return _extract_json(response.text).get("es_validable", "no_válido")

    return _with_retries(call, fallback="error")


# --- 2. Reference fact-check ---------------------------------------------------------
def reference_factcheck(client, claim: str, request: str) -> str:
    from google.genai import types

    def call():
        response = client.models.generate_content(
            model=config.MODEL_REFERENCE,
            contents=config.REFERENCE_PROMPT.format(claim=_text(claim), request=_text(request)),
            config=types.GenerateContentConfig(
                max_output_tokens=300,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        return response.text.strip()

    return _with_retries(call, fallback="error: max retries")


# --- 3. Judge ------------------------------------------------------------------------------
JUDGE_FALLBACK = {"verdict": "unknown", "confidence": 0.0, "theme": "other"}


def validate_judgement(parsed: dict) -> dict:
    """Coerce the judge's JSON into the allowed labels and a confidence in [0, 1]."""
    verdict = str(parsed.get("verdict", "")).strip().lower().replace("-", "_")
    if verdict not in config.VERDICTS:
        verdict = next((v for v in config.VERDICTS if v in verdict), "unknown")
    try:
        confidence = min(1.0, max(0.0, round(float(parsed.get("confidence", 0.5)), 2)))
    except (TypeError, ValueError):
        confidence = 0.5
    theme = str(parsed.get("theme", "")).strip().lower().replace(" ", "_").replace("-", "_")
    if theme not in config.THEMES:
        theme = next((t for t in config.THEMES if t in theme), "other")
    return {"verdict": verdict, "confidence": confidence, "theme": theme}


def judge(client, grok_reply: str, reference: str) -> dict:
    grok_reply, reference = _text(grok_reply), _text(reference)
    if not grok_reply or not reference:
        return dict(JUDGE_FALLBACK)
    from google.genai import types

    def call():
        response = client.models.generate_content(
            model=config.MODEL_JUDGE,
            contents=f"ANALYSIS A:\n{grok_reply}\n\nANALYSIS B:\n{reference}\n\nReturn the JSON object as instructed.",
            config=types.GenerateContentConfig(
                system_instruction=config.JUDGE_SYSTEM_PROMPT, temperature=0, max_output_tokens=2048),
        )
        return validate_judgement(_extract_json(response.text))

    return _with_retries(call, fallback=dict(JUDGE_FALLBACK))


# --- Resumable runner -----------------------------------------------------------------------
def run_resumable(df: pd.DataFrame, row_fn: Callable[[pd.Series], dict], out_cols: list[str],
                  checkpoint: str | Path, every: int = 25, pause: float = 0.3,
                  only: pd.Series | None = None) -> pd.DataFrame:
    """Apply `row_fn` to each row, saving progress to `checkpoint` (CSV keyed by Grok reply id).

    `row_fn` returns a dict with the keys in `out_cols`. `only` is an optional boolean
    mask: rows outside it are left empty (e.g. the reference step only runs on
    fact-checkable claims). Re-running the same call continues where it stopped.
    """
    checkpoint = Path(checkpoint)
    done = (pd.read_csv(checkpoint, dtype={"id": str}).set_index("id")
            if checkpoint.exists() else pd.DataFrame(columns=out_cols).rename_axis("id"))
    todo = df if only is None else df[only]
    todo = todo[~todo["id"].astype(str).isin(done.index)]
    print(f"{len(done)} rows already done, {len(todo)} to go")

    new = []
    for i, (_, row) in enumerate(todo.iterrows(), start=1):
        new.append({"id": str(row["id"]), **row_fn(row)})
        time.sleep(pause)
        if i % every == 0 or i == len(todo):
            done = pd.concat([done, pd.DataFrame(new).set_index("id")])
            done.to_csv(checkpoint)
            new = []
            print(f"  {i}/{len(todo)} saved")

    out = df.copy()
    out["id"] = out["id"].astype(str)
    return out.join(done[out_cols], on="id")


def annotate(threads: pd.DataFrame, client, workdir: str | Path = "checkpoints") -> pd.DataFrame:
    """Run the three steps and return the annotated dataset (fact-checkable claims only)."""
    workdir = Path(workdir)
    workdir.mkdir(exist_ok=True)

    df = run_resumable(threads, lambda r: {"es_validable": is_checkable(client, r["df3_text"])},
                       ["es_validable"], workdir / "1_filter.csv")
    df = df[df["es_validable"] == "válido"].reset_index(drop=True)

    df = run_resumable(df, lambda r: {"gemini_factcheck": reference_factcheck(client, r["df3_text"], r["df2_text"])},
                       ["gemini_factcheck"], workdir / "2_reference.csv")

    def judge_row(r):
        result = judge(client, r["text"], r["gemini_factcheck"])
        return {"comparison_verdict": result["verdict"], "verdict_confidence": result["confidence"],
                "thematic_category": result["theme"]}

    return run_resumable(df, judge_row, ["comparison_verdict", "verdict_confidence", "thematic_category"],
                         workdir / "3_judge.csv", pause=1.0)
