"""Step 1 - Build the corpus of 3-tweet threads from X via Apify.

Each interaction is rebuilt backwards from Grok's reply:
    claim (df3)  <-  user asks @grok (df2)  <-  Grok's reply (df1)
using the `inReplyToId` field of each tweet.
"""
from __future__ import annotations

import pandas as pd

from . import config

# Every content filter off; only the engagement filter changes between steps.
_BASE_FILTERS = {
    f"filter:{name}": False
    for name in [
        "blue_verified", "consumer_video", "has_engagement", "hashtags", "images",
        "links", "media", "mentions", "native_video", "nativeretweets", "news",
        "pro_video", "quote", "replies", "safe", "spaces", "twimg", "videos", "vine",
    ]
} | {"include:nativeretweets": False}

TWEET_FIELDS = [
    "id", "text", "retweetCount", "replyCount", "likeCount", "quoteCount", "viewCount",
    "createdAt", "lang", "bookmarkCount", "conversationId", "inReplyToId",
    "inReplyToUserId", "isConversationControlled", "isPinned", "isReply", "type",
]
AUTHOR_FIELDS = {"id": "author_id", "followers": "author_followers",
                 "following": "author_following", "createdAt": "author_created_at",
                 "isAutomated": "author_isAutomated"}


def search_input(lang: str, max_items: int = config.MAX_ITEMS_PER_SEARCH) -> dict:
    """Actor input for step 1: Grok replies containing verification vocabulary."""
    return _BASE_FILTERS | {"filter:has_engagement": True, "lang": lang,
                            "maxItems": max_items, "searchTerms": config.search_terms(lang)}


def by_ids_input(tweet_ids: list[str], max_items: int | None = None) -> dict:
    """Actor input for steps 2 and 3: fetch specific tweets by ID."""
    payload = _BASE_FILTERS | {"tweetIDs": tweet_ids}
    if max_items is not None:
        payload["maxItems"] = max_items
    return payload


def _field(obj, attr: str, key: str):
    """apify-client returns typed objects in recent versions and dicts in older ones."""
    return getattr(obj, attr) if hasattr(obj, attr) else obj[key]


def run_actor(client, actor_input: dict) -> str:
    """Run the Apify actor and return the run ID (keep it: runs can be re-read later)."""
    run = client.actor(config.APIFY_ACTOR_ID).call(run_input=actor_input)
    run_id = _field(run, "id", "id")
    print(f"Run {run_id} | status {_field(run, 'status', 'status')} | "
          f"dataset {_field(run, 'default_dataset_id', 'defaultDatasetId')}")
    return run_id


def flatten(items) -> pd.DataFrame:
    """Turn raw Apify items into one row per tweet with the fields used in the study."""
    rows = []
    for item in items:
        author = item.get("author") or {}
        row = {field: item.get(field, "") for field in TWEET_FIELDS}
        row |= {new: author.get(old, "") for old, new in AUTHOR_FIELDS.items()}
        rows.append(row)
    return pd.DataFrame(rows, columns=TWEET_FIELDS + list(AUTHOR_FIELDS.values()))


def load_run(client, run_id: str) -> pd.DataFrame:
    """Download the dataset of a finished run."""
    run = client.run(run_id).get()
    items = client.dataset(_field(run, "default_dataset_id", "defaultDatasetId")).iterate_items()
    return flatten(items)


def parent_ids(df: pd.DataFrame) -> list[str]:
    """IDs of the tweets that the rows of `df` reply to."""
    return df["inReplyToId"].dropna().astype(str).drop_duplicates().tolist()


def build_threads(grok: pd.DataFrame, requests: pd.DataFrame, claims: pd.DataFrame) -> pd.DataFrame:
    """Left-join the three levels: one row per Grok reply.

    Columns from the requesting tweet get the prefix `df2_`, columns from the
    claim get `df3_`. Rows whose claim could not be retrieved are dropped.
    """
    grok, requests, claims = grok.copy(), requests.copy(), claims.copy()
    for frame in (grok, requests):
        frame[["id", "inReplyToId"]] = frame[["id", "inReplyToId"]].astype(str)
    claims["id"] = claims["id"].astype(str)

    req = requests.drop_duplicates("id").add_prefix("df2_")
    clm = claims.drop_duplicates("id").add_prefix("df3_")

    merged = (grok.merge(req, left_on="inReplyToId", right_on="df2_id", how="left", validate="m:1")
                  .merge(clm, left_on="df2_inReplyToId", right_on="df3_id", how="left", validate="m:1"))
    assert len(merged) == len(grok), "the joins must not duplicate Grok replies"
    return merged.dropna(subset=["df3_id"]).reset_index(drop=True)


def collect(client, langs=("en", "es")) -> pd.DataFrame:
    """Full collection: step 1 per language, then steps 2 and 3, then the joins."""
    grok = pd.concat([load_run(client, run_actor(client, search_input(lang))) for lang in langs],
                     ignore_index=True)
    requests = load_run(client, run_actor(client, by_ids_input(parent_ids(grok), config.MAX_ITEMS_BY_ID)))
    requests = requests[requests["isReply"] == True]  # noqa: E712 - the request must itself be a reply
    claims = load_run(client, run_actor(client, by_ids_input(parent_ids(requests))))
    return build_threads(grok, requests, claims)
