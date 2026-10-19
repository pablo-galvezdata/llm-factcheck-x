"""Rebuild the study dataset from scratch.

Requires API keys in the environment (see .env.example):
    APIFY_TOKEN       Apify account (the scraper is pay-per-result)
    GEMINI_API_KEY    Google AI Studio

Usage:
    python src/run_pipeline.py collect     # scrape threads -> data/raw/threads.csv
    python src/run_pipeline.py clean       # cleaning funnel -> data/raw/threads_clean.csv
    python src/run_pipeline.py annotate    # Gemini filter + reference + judge -> data/raw/annotated.csv

Note: X content changes over time (deleted tweets, new view counts), so a fresh
run will not reproduce the published sample exactly. The published sample is in
data/annotations.csv.
"""
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from factcheck import annotate, clean, collect  # noqa: E402

RAW = Path("data/raw")


def main(step: str) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    if step == "collect":
        from apify_client import ApifyClient
        threads = collect.collect(ApifyClient(os.environ["APIFY_TOKEN"]))
        threads.to_csv(RAW / "threads.csv", index=False)
        print(f"{len(threads)} threads saved")
    elif step == "clean":
        threads = pd.read_csv(RAW / "threads.csv", dtype=str)
        df, funnel = clean.clean(threads)
        df.to_csv(RAW / "threads_clean.csv", index=False)
        print(funnel.to_string(index=False))
    elif step == "annotate":
        df = pd.read_csv(RAW / "threads_clean.csv", dtype={"id": str})
        out = annotate.annotate(df, annotate.make_client(os.environ.get("GEMINI_API_KEY")), RAW / "checkpoints")
        out.to_csv(RAW / "annotated.csv", index=False)
        print(out["comparison_verdict"].value_counts())
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
