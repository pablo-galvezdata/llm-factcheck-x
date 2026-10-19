"""Step 2 - Cleaning funnel applied to the joined threads.

Each step is logged so the funnel table in the paper can be rebuilt.
The LLM-based filter (claims that cannot be fact-checked) lives in annotate.py.
"""
from __future__ import annotations

import pandas as pd

from . import config


def clean(threads: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (clean threads, funnel log)."""
    df = threads.copy()
    log = [("joined threads", len(df))]

    def step(label: str, mask: pd.Series) -> None:
        nonlocal df
        df = df[mask].copy()
        log.append((label, len(df)))

    claim_author = df["df3_author_id"].astype(str).str.removesuffix(".0")
    step("Grok fact-checking Grok", claim_author != config.GROK_AUTHOR_ID)

    for col, prefix, limit in [("text_length", "", config.MAX_LEN_GROK_REPLY),
                               ("df2_text_length", "df2_", config.MAX_LEN_REQUEST),
                               ("df3_text_length", "df3_", config.MAX_LEN_CLAIM)]:
        df[col] = df[f"{prefix}text"].str.len()
        step(f"{prefix or 'grok_'}text longer than {limit} chars", df[col] <= limit)

    step(f"claim shorter than {config.MIN_LEN_CLAIM} chars (links, media)",
         df["df3_text_length"] >= config.MIN_LEN_CLAIM)

    df = df.drop_duplicates(subset=["id"], keep="first").reset_index(drop=True)
    log.append(("duplicate Grok replies", len(df)))

    funnel = pd.DataFrame(log, columns=["step", "rows_after"])
    funnel["removed"] = (-funnel["rows_after"].diff()).fillna(0).astype(int)
    return df, funnel
