"""Study parameters: collection windows, search keywords, cleaning thresholds,
models and prompts. Values are the ones used in the original study."""

# --- Collection (Apify) -------------------------------------------------------
APIFY_ACTOR_ID = "kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest"
GROK_AUTHOR_ID = "1720665183188922368"

PERIODS = {
    "2025": ("2025-03-01", "2025-06-01"),
    "2026": ("2026-02-01", "2026-05-01"),
}

# Vocabulary typical of a verification reply. Each keyword is searched in both
# periods as: from:grok "<keyword>" filter:replies since:<start> until:<end>
GROK_REPLY_KEYWORDS = {
    "en": [
        "true", "not true", "false", "accurate", "inaccurate", "correct", "incorrect",
        "real", "Yes, there", "No, there", "public records show",
        "based on available information", "based on the information available",
        "I could not verify", "I cannot verify", "unable to verify", "verified",
        "unverified", "claim is", "source", "sources", "according to", "reported by",
        "fact check",
    ],
    "es": [
        "verdadero", "falso", "no es cierto", "es cierto", "correcto", "incorrecto",
        "real", "no es real", "registros públicos muestran", "evidencia", "pruebas",
        "según la información disponible", "basado en la información disponible",
        "no pude verificar", "no puedo verificar", "no se puede verificar",
        "verificado", "no verificado", "reportado por",
    ],
}
MAX_ITEMS_PER_SEARCH = 100   # step 1: Grok replies per search term
MAX_ITEMS_BY_ID = 5          # step 2: value used when fetching the requesting tweets

# --- Cleaning -------------------------------------------------------------------
MAX_LEN_GROK_REPLY = 2000    # characters
MAX_LEN_REQUEST = 1000
MAX_LEN_CLAIM = 3000
MIN_LEN_CLAIM = 60           # shorter claims are mostly bare links or media references

# --- LLM annotation (Gemini) ----------------------------------------------------
MODEL_FILTER = "gemini-3.1-flash-lite"     # is the claim fact-checkable?
MODEL_REFERENCE = "gemini-3.1-flash-lite"  # independent fact-check, with Google Search
MODEL_JUDGE = "gemini-3.5-flash"           # compares Grok vs. reference (different model on purpose)
MAX_RETRIES = 3

VALIDATION_PROMPT = """Analiza si este tweet contiene una afirmación fáctica concreta
que pueda verificarse o refutarse con evidencia.

TWEET:
{claim}

Responde SOLO con JSON:
{{"es_validable": "válido" o "no_válido"}}"""

REFERENCE_PROMPT = """Eres un fact-checker experto. Un usuario ha pedido verificar la veracidad de un tweet.

TWEET SIENDO CUESTIONADO:
{claim}

PREGUNTA DEL USUARIO:
{request}


Responde en el mismo idioma que el tweet siendo cuestionado
Realiza un fact-checking riguroso. Analiza la afirmación, evalúa su veracidad con lo que sabes, e indica si es verdadera, falsa, engañosa o no verificable. Explica tu razonamiento de forma clara y concisa.


IMPORTANTE: Tu respuesta debe ser completa y autocontenida, de aproximadamente entre 400 y 600 carácteres. Asegúrate de cerrar siempre tu conclusión; no dejes frases a medias."""

VERDICTS = ["same", "mostly_same", "unknown", "slight_diff", "disparity"]
THEMES = [
    "politics", "government_policy", "war", "health_medicine", "science_technology",
    "economy_finance", "crime_justice", "sports", "celebrities_entertainment",
    "environment_climate", "social_media_viral", "history_education",
    "conspiracy_misinformation", "other",
]

# The judge prompt is written in English on purpose (the reference prompt is in
# Spanish) to add distance between the two annotation steps.
JUDGE_SYSTEM_PROMPT = f"""You are a fact-check analyst. Given two fact-check analyses (A and B) of the same original claim, you must return a JSON object with exactly three keys:

1. "verdict"
   How well do the overall conclusions of A and B agree?
   Choose exactly one of: {sorted(VERDICTS)}

   Definitions:
   - same          : both reach the same conclusion
   - mostly_same   : broadly agree, minor nuance or detail differences
   - unknown       : one or both are inconclusive / not enough info to compare
   - slight_diff   : lean different ways but not a strong contradiction
   - disparity     : clearly opposite or contradictory conclusions

2. "confidence"
   How confident are you in your verdict? Float between 0.0 (no idea) and 1.0 (completely certain).
   Use 0.9–1.0 only when both texts are unambiguous and directly comparable.
   Use 0.5–0.7 for ambiguous, vague, or off-topic texts.
   Use below 0.5 when you are genuinely unsure.

3. "theme"
   What is the topic of this fact-check conversation?
   Choose exactly one of: {sorted(THEMES)}

   Definitions:
   - politics                  : elections, voting, political figures, parties
   - government_policy         : laws, regulations, public administration, budgets
   - war                       : armed conflicts, military operations, geopolitics
   - health_medicine           : diseases, vaccines, treatments, public health
   - science_technology        : AI, space, research, innovation, tech companies
   - economy_finance           : markets, crypto, trade, inflation, corporate news
   - crime_justice             : arrests, trials, law enforcement, fraud
   - sports                    : any sport, athlete, or competition
   - celebrities_entertainment : actors, musicians, influencers, pop culture
   - environment_climate       : climate change, natural disasters, ecology
   - social_media_viral        : viral posts, platform moderation, online trends
   - history_education         : historical events, academic claims, anniversaries
   - conspiracy_misinformation : conspiracy theories, hoaxes, disinformation
   - other                     : does not fit any category above

Output ONLY valid JSON, no markdown, no explanation. Example:
{{"verdict": "mostly_same", "confidence": 0.85, "theme": "sports"}}"""


def search_terms(lang: str) -> list[str]:
    """Search queries for step 1, in the original order (keyword x period)."""
    return [
        f'from:grok "{kw}" filter:replies since:{start} until:{end}'
        for kw in GROK_REPLY_KEYWORDS[lang]
        for start, end in PERIODS.values()
    ]
