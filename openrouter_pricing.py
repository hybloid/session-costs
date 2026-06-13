#!/usr/bin/env python3
import json
import time
import urllib.request
from decimal import Decimal
from pathlib import Path

MODELS_URL = "https://openrouter.ai/api/v1/models"
CACHE_PATH = Path("~/.cache/session-costs/openrouter-price-snapshot.json").expanduser()
CACHE_TTL_SECONDS = 12 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 10

_CATALOG_CACHE = None

FALLBACK_SNAPSHOT = {
    "fetched_at": 0,
    "entries": [
        {
            "id": "anthropic/claude-fable-5",
            "canonical_slug": "anthropic/claude-5-fable-20260609",
            "display_name": "Anthropic: Claude Fable 5",
            "prompt_token_price_usd": "0.00001",
            "completion_token_price_usd": "0.00005",
            "cache_read_token_price_usd": "0.000001",
            "cache_write_token_price_usd": "0.0000125",
        },
        {
            "id": "anthropic/claude-mythos-5",
            "canonical_slug": "anthropic/claude-5-mythos-20260609",
            "display_name": "Anthropic: Claude Mythos 5",
            "prompt_token_price_usd": "0.00001",
            "completion_token_price_usd": "0.00005",
            "cache_read_token_price_usd": "0.000001",
            "cache_write_token_price_usd": "0.0000125",
        },
        {
            "id": "anthropic/claude-opus-4.8",
            "canonical_slug": "anthropic/claude-4.8-opus-20260528",
            "display_name": "Anthropic: Claude Opus 4.8",
            "prompt_token_price_usd": "0.000005",
            "completion_token_price_usd": "0.000025",
            "cache_read_token_price_usd": "0.0000005",
            "cache_write_token_price_usd": "0.00000625",
        },
        {
            "id": "anthropic/claude-opus-4.7",
            "canonical_slug": "anthropic/claude-4.7-opus-20260416",
            "display_name": "Anthropic: Claude Opus 4.7",
            "prompt_token_price_usd": "0.000005",
            "completion_token_price_usd": "0.000025",
            "cache_read_token_price_usd": "0.0000005",
            "cache_write_token_price_usd": "0.00000625",
        },
        {
            "id": "anthropic/claude-opus-4.6",
            "canonical_slug": "anthropic/claude-4.6-opus-20260205",
            "display_name": "Anthropic: Claude Opus 4.6",
            "prompt_token_price_usd": "0.000005",
            "completion_token_price_usd": "0.000025",
            "cache_read_token_price_usd": "0.0000005",
            "cache_write_token_price_usd": "0.00000625",
        },
        {
            "id": "anthropic/claude-opus-4.5",
            "canonical_slug": "anthropic/claude-4.5-opus-20251124",
            "display_name": "Anthropic: Claude Opus 4.5",
            "prompt_token_price_usd": "0.000005",
            "completion_token_price_usd": "0.000025",
            "cache_read_token_price_usd": "0.0000005",
            "cache_write_token_price_usd": "0.00000625",
        },
        {
            "id": "anthropic/claude-opus-4.1",
            "canonical_slug": "anthropic/claude-4.1-opus-20250805",
            "display_name": "Anthropic: Claude Opus 4.1",
            "prompt_token_price_usd": "0.000015",
            "completion_token_price_usd": "0.000075",
            "cache_read_token_price_usd": "0.0000015",
            "cache_write_token_price_usd": "0.00001875",
        },
        {
            "id": "anthropic/claude-opus-4",
            "canonical_slug": "anthropic/claude-4-opus-20250522",
            "display_name": "Anthropic: Claude Opus 4",
            "prompt_token_price_usd": "0.000015",
            "completion_token_price_usd": "0.000075",
            "cache_read_token_price_usd": "0.0000015",
            "cache_write_token_price_usd": "0.00001875",
        },
        {
            "id": "anthropic/claude-sonnet-4.6",
            "canonical_slug": "anthropic/claude-4.6-sonnet-20260217",
            "display_name": "Anthropic: Claude Sonnet 4.6",
            "prompt_token_price_usd": "0.000003",
            "completion_token_price_usd": "0.000015",
            "cache_read_token_price_usd": "0.0000003",
            "cache_write_token_price_usd": "0.00000375",
        },
        {
            "id": "anthropic/claude-sonnet-4.5",
            "canonical_slug": "anthropic/claude-4.5-sonnet-20250929",
            "display_name": "Anthropic: Claude Sonnet 4.5",
            "prompt_token_price_usd": "0.000003",
            "completion_token_price_usd": "0.000015",
            "cache_read_token_price_usd": "0.0000003",
            "cache_write_token_price_usd": "0.00000375",
        },
        {
            "id": "anthropic/claude-sonnet-4",
            "canonical_slug": "anthropic/claude-4-sonnet-20250522",
            "display_name": "Anthropic: Claude Sonnet 4",
            "prompt_token_price_usd": "0.000003",
            "completion_token_price_usd": "0.000015",
            "cache_read_token_price_usd": "0.0000003",
            "cache_write_token_price_usd": "0.00000375",
        },
        {
            "id": "anthropic/claude-haiku-4.5",
            "canonical_slug": "anthropic/claude-4.5-haiku-20251001",
            "display_name": "Anthropic: Claude Haiku 4.5",
            "prompt_token_price_usd": "0.000001",
            "completion_token_price_usd": "0.000005",
            "cache_read_token_price_usd": "0.0000001",
            "cache_write_token_price_usd": "0.00000125",
        },
        {
            "id": "anthropic/claude-3.5-haiku",
            "canonical_slug": "anthropic/claude-3.5-haiku",
            "display_name": "Anthropic: Claude 3.5 Haiku",
            "prompt_token_price_usd": "0.0000008",
            "completion_token_price_usd": "0.000004",
            "cache_read_token_price_usd": "0.00000008",
            "cache_write_token_price_usd": "0.000001",
        },
        {
            "id": "openai/gpt-5.5",
            "canonical_slug": "openai/gpt-5.5-20260423",
            "display_name": "OpenAI: GPT-5.5",
            "prompt_token_price_usd": "0.000005",
            "completion_token_price_usd": "0.00003",
            "cache_read_token_price_usd": "0.0000005",
            "cache_write_token_price_usd": None,
        },
        {
            "id": "openai/gpt-5.4",
            "canonical_slug": "openai/gpt-5.4-20260305",
            "display_name": "OpenAI: GPT-5.4",
            "prompt_token_price_usd": "0.0000025",
            "completion_token_price_usd": "0.000015",
            "cache_read_token_price_usd": "0.00000025",
            "cache_write_token_price_usd": None,
        },
        {
            "id": "openai/gpt-5.4-mini",
            "canonical_slug": "openai/gpt-5.4-mini-20260317",
            "display_name": "OpenAI: GPT-5.4 Mini",
            "prompt_token_price_usd": "0.00000075",
            "completion_token_price_usd": "0.0000045",
            "cache_read_token_price_usd": "0.000000075",
            "cache_write_token_price_usd": None,
        },
        {
            "id": "openai/gpt-5-codex",
            "canonical_slug": "openai/gpt-5-codex",
            "display_name": "OpenAI: GPT-5 Codex",
            "prompt_token_price_usd": "0.00000125",
            "completion_token_price_usd": "0.00001",
            "cache_read_token_price_usd": "0.000000125",
            "cache_write_token_price_usd": None,
        },
        {
            "id": "openai/gpt-5-mini",
            "canonical_slug": "openai/gpt-5-mini-2025-08-07",
            "display_name": "OpenAI: GPT-5 Mini",
            "prompt_token_price_usd": "0.00000025",
            "completion_token_price_usd": "0.000002",
            "cache_read_token_price_usd": "0.000000025",
            "cache_write_token_price_usd": None,
        },
        {
            "id": "openai/gpt-5-nano",
            "canonical_slug": "openai/gpt-5-nano-2025-08-07",
            "display_name": "OpenAI: GPT-5 Nano",
            "prompt_token_price_usd": "0.00000005",
            "completion_token_price_usd": "0.0000004",
            "cache_read_token_price_usd": "0.00000001",
            "cache_write_token_price_usd": None,
        },
        {
            "id": "openai/gpt-5.1-codex-mini",
            "canonical_slug": "openai/gpt-5.1-codex-mini-20251113",
            "display_name": "OpenAI: GPT-5.1 Codex Mini",
            "prompt_token_price_usd": "0.00000025",
            "completion_token_price_usd": "0.000002",
            "cache_read_token_price_usd": "0.000000025",
            "cache_write_token_price_usd": None,
        },
    ],
}


def normalize_openrouter_model_name(value):
    if not value:
        return None

    normalized = []
    last_was_separator = False
    for ch in value.lower().strip():
        if ch.isalnum():
            normalized.append(ch)
            last_was_separator = False
        elif not last_was_separator:
            normalized.append("-")
            last_was_separator = True

    result = "".join(normalized).strip("-")
    return result or None


def build_normalized_model_names(value):
    if not value:
        return set()

    trimmed = value.strip()
    slash_parts = [part for part in trimmed.split("/") if part]
    candidates = [trimmed]
    for index in range(len(slash_parts)):
        candidates.append("/".join(slash_parts[index:]))

    normalized = []
    for candidate in candidates:
        item = normalize_openrouter_model_name(candidate)
        if item and item not in normalized:
            normalized.append(item)
    return set(normalized)


def create_entry(entry):
    id_value = entry.get("id")
    if not id_value:
        return None
    canonical_slug = entry.get("canonical_slug")
    display_name = entry.get("display_name")
    normalized_names = set()
    normalized_names.update(build_normalized_model_names(id_value))
    normalized_names.update(build_normalized_model_names(canonical_slug))
    normalized_names.update(build_normalized_model_names(display_name))
    return {
        "id": id_value,
        "canonical_slug": canonical_slug,
        "display_name": display_name,
        "normalized_names": normalized_names,
        "prompt_token_price_usd": entry.get("prompt_token_price_usd"),
        "completion_token_price_usd": entry.get("completion_token_price_usd"),
        "cache_read_token_price_usd": entry.get("cache_read_token_price_usd"),
        "cache_write_token_price_usd": entry.get("cache_write_token_price_usd"),
    }


def parse_snapshot(payload, fetched_at=None):
    entries = []
    for item in payload.get("data", []):
        pricing = item.get("pricing") or {}
        entry = create_entry(
            {
                "id": item.get("id"),
                "canonical_slug": item.get("canonical_slug"),
                "display_name": item.get("name"),
                "prompt_token_price_usd": pricing.get("prompt"),
                "completion_token_price_usd": pricing.get("completion"),
                "cache_read_token_price_usd": pricing.get("input_cache_read"),
                "cache_write_token_price_usd": pricing.get("input_cache_write"),
            }
        )
        if entry:
            entries.append(entry)
    return {"fetched_at": int(fetched_at or time.time()), "entries": entries}


def fallback_snapshot():
    return {"fetched_at": 0, "entries": [create_entry(entry) for entry in FALLBACK_SNAPSHOT["entries"] if create_entry(entry)]}


def load_cached_snapshot(cache_path=CACHE_PATH):
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    entries = []
    for entry in payload.get("entries", []):
        created = create_entry(entry)
        if created:
            entries.append(created)
    if not entries:
        return None
    return {"fetched_at": int(payload.get("fetched_at") or 0), "entries": entries}


def save_snapshot(snapshot, cache_path=CACHE_PATH):
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": snapshot.get("fetched_at") or int(time.time()),
            "entries": [
                {
                    "id": entry["id"],
                    "canonical_slug": entry.get("canonical_slug"),
                    "display_name": entry.get("display_name"),
                    "prompt_token_price_usd": entry.get("prompt_token_price_usd"),
                    "completion_token_price_usd": entry.get("completion_token_price_usd"),
                    "cache_read_token_price_usd": entry.get("cache_read_token_price_usd"),
                    "cache_write_token_price_usd": entry.get("cache_write_token_price_usd"),
                }
                for entry in snapshot.get("entries", [])
            ],
        }
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return


def fetch_snapshot(url=MODELS_URL, timeout=REQUEST_TIMEOUT_SECONDS):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    return parse_snapshot(payload)


def resolve_catalog(force_refresh=False, now=None, cache_path=CACHE_PATH):
    global _CATALOG_CACHE
    if not force_refresh and _CATALOG_CACHE is not None:
        return _CATALOG_CACHE

    now = now or time.time()
    cached = load_cached_snapshot(cache_path)
    if not force_refresh and cached and now - cached.get("fetched_at", 0) < CACHE_TTL_SECONDS:
        _CATALOG_CACHE = cached
        return cached

    try:
        fresh = fetch_snapshot()
        save_snapshot(fresh, cache_path)
        _CATALOG_CACHE = fresh
        return fresh
    except Exception:
        if cached:
            _CATALOG_CACHE = cached
            return cached
        _CATALOG_CACHE = fallback_snapshot()
        return _CATALOG_CACHE


def match_openrouter_model(model_id, snapshot=None):
    snapshot = snapshot or resolve_catalog()
    normalized_names = build_normalized_model_names(model_id)
    if not normalized_names:
        return None

    exact_matches = []
    for entry in snapshot.get("entries", []):
        if entry["normalized_names"] & normalized_names:
            if entry not in exact_matches:
                exact_matches.append(entry)
    if len(exact_matches) == 1:
        return exact_matches[0]

    prefix_matches = []
    for entry in snapshot.get("entries", []):
        if any(
            query.startswith(candidate) or candidate.startswith(query)
            for candidate in entry["normalized_names"]
            for query in normalized_names
        ):
            if entry not in prefix_matches:
                prefix_matches.append(entry)
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    return None


def cost_contribution(tokens, price_per_token_usd):
    if not tokens:
        return Decimal("0")
    if price_per_token_usd is None:
        return None
    return Decimal(str(price_per_token_usd)) * Decimal(tokens)


def calculate_estimated_cost(model_id, input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0, snapshot=None):
    entry = match_openrouter_model(model_id, snapshot=snapshot)
    if not entry:
        return None, None

    parts = [
        cost_contribution(input_tokens, entry.get("prompt_token_price_usd")),
        cost_contribution(output_tokens, entry.get("completion_token_price_usd")),
        cost_contribution(cache_read_tokens, entry.get("cache_read_token_price_usd")),
        cost_contribution(cache_write_tokens, entry.get("cache_write_token_price_usd")),
    ]
    if any(part is None for part in parts):
        return entry, None
    total = sum(parts, Decimal("0"))
    return entry, float(total)
