# Data

Tweet text and author data are **not** included. Only the tweet IDs, public view and engagement counts, and the labels produced by the LLM pipeline are published. The tweets can be rehydrated from their IDs by anyone with X access, subject to deletions.

## `annotations.csv` (2,493 rows)

One row per interaction (claim → user request → Grok's reply) that passed cleaning and the fact-checkability filter.

| Column | Description |
|---|---|
| `grok_reply_id` | ID of Grok's reply |
| `request_tweet_id` | ID of the tweet where the user invokes @grok |
| `claim_tweet_id` | ID of the post being fact-checked |
| `createdAt` | Timestamp of Grok's reply (UTC). Defines the collection period |
| `lang` | Language of Grok's reply as reported by X (`en`, `es`, others) |
| `viewCount`, `likeCount`, `retweetCount`, `replyCount`, `quoteCount`, `bookmarkCount` | Engagement of Grok's reply at scraping time |
| `claim_viewCount` | Views of the claim at scraping time |
| `comparison_verdict` | Judge model's rating of Grok vs. reference fact-check: `same`, `mostly_same`, `slight_diff`, `disparity`, `unknown` |
| `verdict_confidence` | Judge's confidence in that rating (0–1) |
| `thematic_category` | One of 14 topics assigned by the judge |

The analysis drops `unknown` verdicts (83) and languages other than English and Spanish (57), which leaves **2,353** rows.

## `qualitative_coding.csv` (80 rows)

Manual review of a sample of disagreements between Grok and Gemini.

| Column | Values |
|---|---|
| `case_id`, `theme`, `lang`, `judge_confidence` | Case metadata |
| `disagreement_reason` | `temporal` (knowledge cutoff), `ambiguity`, `x_source` (Grok relied on X posts), `gemini_hallucination`, `grok_hallucination`, `topic_bias`, `opinion_vs_fact` |
| `more_accurate` | `grok`, `gemini`, `both_right`, `both_wrong`, `undetermined` |

Codes were translated from the original Spanish coding sheet; two misspellings of `ambiguedad` were merged into `ambiguity`.
