"""Lightweight, dependency-free, lexicon-based sentiment baseline (VADER-inspired).

It handles negation and intensity boosters on a small finance/business lexicon.
It is a transparent analytical signal, NOT a market forecast.
"""
from __future__ import annotations

import math
import re

ENGINE_NAME = "lexicon-baseline-v1 (rule-based, VADER-inspired)"

POSITIVE = {
    "surge": 2.5, "surges": 2.5, "soar": 2.8, "soars": 2.8, "rally": 2.2, "rallies": 2.2, "gain": 1.6,
    "gains": 1.6, "rise": 1.2, "rises": 1.2, "rose": 1.2, "jump": 1.8, "jumps": 1.8, "record": 1.4,
    "growth": 1.6, "grow": 1.4, "grows": 1.4, "beat": 1.6, "beats": 1.6, "strong": 1.5, "stronger": 1.6,
    "boost": 1.7, "boosts": 1.7, "profit": 1.5, "profits": 1.5, "win": 1.6, "wins": 1.6, "upgrade": 1.6,
    "optimism": 1.8, "optimistic": 1.8, "recovery": 1.6, "recover": 1.4, "breakthrough": 2.2,
    "expands": 1.3, "expansion": 1.3, "approve": 1.3, "approves": 1.3, "approved": 1.3, "success": 1.8,
    "improve": 1.4, "improves": 1.4, "improved": 1.4, "launch": 0.8, "launches": 0.8, "invest": 0.9,
    "investment": 0.9, "easing": 1.0, "cooling": 0.6, "resilient": 1.5, "rebound": 1.7, "milestone": 1.5,
}
NEGATIVE = {
    "fall": -1.4, "falls": -1.4, "fell": -1.4, "drop": -1.6, "drops": -1.6, "plunge": -2.8, "plunges": -2.8,
    "slump": -2.4, "slumps": -2.4, "tumble": -2.4, "tumbles": -2.4, "crash": -3.0, "loss": -1.8,
    "losses": -1.8, "lose": -1.6, "loses": -1.6, "weak": -1.5, "weaker": -1.6, "cut": -1.2, "cuts": -1.2,
    "layoffs": -2.2, "layoff": -2.2, "fear": -1.9, "fears": -1.9, "risk": -1.0, "risks": -1.0,
    "recession": -2.5, "inflation": -1.0, "warn": -1.6, "warns": -1.6, "warning": -1.6, "probe": -1.3,
    "investigation": -1.4, "lawsuit": -1.6, "sues": -1.6, "fine": -1.2, "fined": -1.5, "ban": -1.4,
    "bans": -1.4, "tariff": -1.1, "tariffs": -1.1, "sanctions": -1.5, "decline": -1.5, "declines": -1.5,
    "downgrade": -1.7, "default": -2.2, "bankruptcy": -3.0, "crisis": -2.4, "concern": -1.2,
    "concerns": -1.2, "uncertainty": -1.4, "volatile": -1.3, "volatility": -1.3, "shortage": -1.6,
    "outage": -1.7, "breach": -2.2, "hack": -2.0, "slowdown": -1.8, "worst": -2.3, "struggle": -1.5,
    "struggles": -1.5, "halt": -1.4, "halts": -1.4, "miss": -1.4, "misses": -1.4,
}
LEXICON = {**POSITIVE, **NEGATIVE}
NEGATIONS = {"not", "no", "never", "without", "fails", "failed", "isn't", "wasn't", "won't", "doesn't", "don't"}
BOOSTERS = {"sharply": 0.3, "significantly": 0.25, "major": 0.2, "huge": 0.3, "massive": 0.3, "slightly": -0.25}

_WORD = re.compile(r"[a-z']+")
THRESHOLD = 0.1


def score_text(text: str) -> float:
    """Return a compound score in [-1, 1]."""
    words = _WORD.findall((text or "").lower())
    total = 0.0
    for i, w in enumerate(words):
        if w not in LEXICON:
            continue
        val = LEXICON[w]
        window = words[max(0, i - 3): i]
        for b in window:
            if b in BOOSTERS:
                val *= 1 + BOOSTERS[b]
        if any(n in window for n in NEGATIONS):
            val *= -0.74
        total += val
    return round(total / math.sqrt(total * total + 15), 4) if total else 0.0


def label_for(score: float) -> str:
    if score >= THRESHOLD:
        return "positive"
    if score <= -THRESHOLD:
        return "negative"
    return "neutral"


def analyze(text: str) -> tuple[float, str]:
    s = score_text(text)
    return s, label_for(s)
