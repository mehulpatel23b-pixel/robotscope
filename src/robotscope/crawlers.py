"""Catalog of well-known search and AI crawler user-agents (Q3/Q4 2026).

`kind` buckets:
  training   -> collects content for model training sets
  search     -> powers AI answers / search products
  agent      -> fetches pages on behalf of a live user action
  baseline   -> classic web search (kept for contrast in reports)
"""

from __future__ import annotations

from typing import Dict, List

CRAWLERS: List[Dict[str, str]] = [
    # --- OpenAI ---
    {"token": "gptbot", "name": "GPTBot", "company": "OpenAI",
     "kind": "training", "note": "Crawls content for OpenAI model training."},
    {"token": "oai-searchbot", "name": "OAI-SearchBot", "company": "OpenAI",
     "kind": "search", "note": "Powers SearchGPT / ChatGPT search results."},
    {"token": "chatgpt-user", "name": "ChatGPT-User", "company": "OpenAI",
     "kind": "agent", "note": "Fetches a page when a user action triggers browsing."},
    # --- Anthropic ---
    {"token": "claudebot", "name": "ClaudeBot", "company": "Anthropic",
     "kind": "training", "note": "Crawls content for Claude model training."},
    {"token": "claude-web", "name": "Claude-Web", "company": "Anthropic",
     "kind": "agent", "note": "Older browsing user-agent for Claude web fetches."},
    {"token": "claude-searchbot", "name": "Claude-SearchBot", "company": "Anthropic",
     "kind": "search", "note": "Powers Claude's online search results."},
    # --- Common Crawl ---
    {"token": "ccbot", "name": "CCBot", "company": "Common Crawl",
     "kind": "training", "note": "Open corpus crawl that feeds many LLM training sets."},
    # --- Google / Microsoft / Apple / Amazon ---
    {"token": "google-extended", "name": "Google-Extended", "company": "Google",
     "kind": "training", "note": "Controls Gemini training access; separate from Googlebot."},
    {"token": "googlebot", "name": "Googlebot", "company": "Google",
     "kind": "baseline", "note": "Classic Google web-search crawler."},
    {"token": "bingbot", "name": "bingbot", "company": "Microsoft",
     "kind": "baseline", "note": "Classic Bing web-search crawler."},
    {"token": "applebot-extended", "name": "Applebot-Extended", "company": "Apple",
     "kind": "training", "note": "Crawls for Apple's AI/LLM features."},
    {"token": "applebot", "name": "Applebot", "company": "Apple",
     "kind": "baseline", "note": "Apple's web crawler incl. Siri suggestions."},
    {"token": "amazonbot", "name": "Amazonbot", "company": "Amazon",
     "kind": "training", "note": "Feeds Alexa AI and Amazon model training."},
    # --- Meta ---
    {"token": "meta-externalagent", "name": "meta-externalagent", "company": "Meta",
     "kind": "training", "note": "Meta's AI training crawler."},
    {"token": "facebookbot", "name": "FacebookBot", "company": "Meta",
     "kind": "baseline", "note": "Link preview / Open Graph fetcher."},
    # --- ByteDance / Perplexity / DuckDuckGo / You / Cohere ---
    {"token": "bytespider", "name": "Bytespider", "company": "ByteDance",
     "kind": "training", "note": "High-volume crawler; large share of AI-bot traffic."},
    {"token": "perplexitybot", "name": "PerplexityBot", "company": "Perplexity",
     "kind": "search", "note": "Powers Perplexity search answers."},
    {"token": "perplexity-user", "name": "Perplexity-User", "company": "Perplexity",
     "kind": "agent", "note": "Fetches pages for Perplexity user actions."},
    {"token": "duckassistbot", "name": "DuckAssistBot", "company": "DuckDuckGo",
     "kind": "search", "note": "Feeds DuckDuckGo AI assist answers."},
    {"token": "youbot", "name": "YouBot", "company": "You.com",
     "kind": "search", "note": "Powers You.com AI search."},
    {"token": "cohere-ai", "name": "cohere-ai", "company": "Cohere",
     "kind": "training", "note": "Cohere model training and evaluation."},
    # --- Datasets / mining ---
    {"token": "diffbot", "name": "Diffbot", "company": "Diffbot",
     "kind": "training", "note": "Knowledge-graph extraction service."},
    {"token": "omgilibot", "name": "Omgilibot", "company": "Webz",
     "kind": "training", "note": "News/media corpus mining used for LLM training."},
    {"token": "img2dataset", "name": "img2dataset", "company": "LAION",
     "kind": "training", "note": "Bulk image scraping used to build training sets."},
]


def by_token(token: str) -> Dict[str, str]:
    for c in CRAWLERS:
        if c["token"] == token.lower():
            return c
    raise KeyError(f"unknown crawler token: {token!r}")


def resolve_names(spec: str) -> List[str]:
    """Resolve a comma-separated list of names/tokens into canonical tokens.

    Accepts either the user-agent token or the display name,
    case-insensitively. Unknown entries are kept as-is (user may want to
    probe a custom user-agent).
    """
    out = []
    for raw in [s.strip() for s in spec.split(",") if s.strip()]:
        low = raw.lower()
        hit = next((c["token"] for c in CRAWLERS
                    if low in (c["token"], c["name"].lower())), low)
        if hit not in out:
            out.append(hit)
    return out
