#!/usr/bin/env python3
from decimal import Decimal

_PRICING_CATALOG = None


FIXED_PRICING_TABLE = [
    {
        "id": "anthropic/claude-fable-5",
        "canonical_slug": "anthropic/claude-5-fable-20260609",
        "display_name": "Anthropic: Claude Fable 5",
        "prompt_token_price_usd": "0.00001",
        "completion_token_price_usd": "0.00005",
        "cache_read_token_price_usd": "0.000001",
        "cache_write_token_price_usd": "0.0000125",
        "cache_write_5m_token_price_usd": "0.0000125",
        "cache_write_1h_token_price_usd": "0.00002",
        "price_source": "legacy_static",
    },
    {
        "id": "anthropic/claude-mythos-5",
        "canonical_slug": "anthropic/claude-5-mythos-20260609",
        "display_name": "Anthropic: Claude Mythos 5",
        "prompt_token_price_usd": "0.00001",
        "completion_token_price_usd": "0.00005",
        "cache_read_token_price_usd": "0.000001",
        "cache_write_token_price_usd": "0.0000125",
        "cache_write_5m_token_price_usd": "0.0000125",
        "cache_write_1h_token_price_usd": "0.00002",
        "price_source": "legacy_static",
    },
    {
        "id": "anthropic/claude-opus-4.8",
        "canonical_slug": "anthropic/claude-4.8-opus-20260528",
        "display_name": "Anthropic: Claude Opus 4.8",
        "prompt_token_price_usd": "0.000005",
        "completion_token_price_usd": "0.000025",
        "cache_read_token_price_usd": "0.0000005",
        "cache_write_token_price_usd": "0.00000625",
        "cache_write_5m_token_price_usd": "0.00000625",
        "cache_write_1h_token_price_usd": "0.00001",
        "price_source": "credits_api_static",
    },
    {
        "id": "anthropic/claude-opus-4.7",
        "canonical_slug": "anthropic/claude-4.7-opus-20260416",
        "display_name": "Anthropic: Claude Opus 4.7",
        "prompt_token_price_usd": "0.000005",
        "completion_token_price_usd": "0.000025",
        "cache_read_token_price_usd": "0.0000005",
        "cache_write_token_price_usd": "0.00000625",
        "cache_write_5m_token_price_usd": "0.00000625",
        "cache_write_1h_token_price_usd": "0.00001",
        "price_source": "credits_api_static",
    },
    {
        "id": "anthropic/claude-opus-4.6",
        "canonical_slug": "anthropic/claude-4.6-opus-20260205",
        "display_name": "Anthropic: Claude Opus 4.6",
        "prompt_token_price_usd": "0.000005",
        "completion_token_price_usd": "0.000025",
        "cache_read_token_price_usd": "0.0000005",
        "cache_write_token_price_usd": "0.00000625",
        "cache_write_5m_token_price_usd": "0.00000625",
        "cache_write_1h_token_price_usd": "0.00001",
        "price_source": "credits_api_static",
    },
    {
        "id": "anthropic/claude-opus-4.5",
        "canonical_slug": "anthropic/claude-4.5-opus-20251124",
        "display_name": "Anthropic: Claude Opus 4.5",
        "prompt_token_price_usd": "0.000005",
        "completion_token_price_usd": "0.000025",
        "cache_read_token_price_usd": "0.0000005",
        "cache_write_token_price_usd": "0.00000625",
        "cache_write_5m_token_price_usd": "0.00000625",
        "cache_write_1h_token_price_usd": "0.00001",
        "price_source": "credits_api_static",
    },
    {
        "id": "anthropic/claude-opus-4.1",
        "canonical_slug": "anthropic/claude-4.1-opus-20250805",
        "display_name": "Anthropic: Claude Opus 4.1",
        "prompt_token_price_usd": "0.000015",
        "completion_token_price_usd": "0.000075",
        "cache_read_token_price_usd": "0.0000015",
        "cache_write_token_price_usd": "0.00001875",
        "cache_write_5m_token_price_usd": "0.00001875",
        "cache_write_1h_token_price_usd": "0.00003",
        "price_source": "credits_api_static",
    },
    {
        "id": "anthropic/claude-opus-4",
        "canonical_slug": "anthropic/claude-4-opus-20250522",
        "display_name": "Anthropic: Claude Opus 4",
        "prompt_token_price_usd": "0.000015",
        "completion_token_price_usd": "0.000075",
        "cache_read_token_price_usd": "0.0000015",
        "cache_write_token_price_usd": "0.00001875",
        "cache_write_5m_token_price_usd": "0.00001875",
        "cache_write_1h_token_price_usd": "0.00003",
        "price_source": "legacy_static",
    },
    {
        "id": "anthropic/claude-sonnet-4.6",
        "canonical_slug": "anthropic/claude-4.6-sonnet-20260217",
        "display_name": "Anthropic: Claude Sonnet 4.6",
        "prompt_token_price_usd": "0.000003",
        "completion_token_price_usd": "0.000015",
        "cache_read_token_price_usd": "0.0000003",
        "cache_write_token_price_usd": "0.00000375",
        "cache_write_5m_token_price_usd": "0.00000375",
        "cache_write_1h_token_price_usd": "0.000006",
        "price_source": "credits_api_static",
    },
    {
        "id": "anthropic/claude-sonnet-4.5",
        "canonical_slug": "anthropic/claude-4.5-sonnet-20250929",
        "display_name": "Anthropic: Claude Sonnet 4.5",
        "prompt_token_price_usd": "0.000003",
        "completion_token_price_usd": "0.000015",
        "cache_read_token_price_usd": "0.0000003",
        "cache_write_token_price_usd": "0.00000375",
        "cache_write_5m_token_price_usd": "0.00000375",
        "cache_write_1h_token_price_usd": "0.000006",
        "price_source": "credits_api_static",
    },
    {
        "id": "anthropic/claude-sonnet-4",
        "canonical_slug": "anthropic/claude-4-sonnet-20250522",
        "display_name": "Anthropic: Claude Sonnet 4",
        "prompt_token_price_usd": "0.000003",
        "completion_token_price_usd": "0.000015",
        "cache_read_token_price_usd": "0.0000003",
        "cache_write_token_price_usd": "0.00000375",
        "cache_write_5m_token_price_usd": "0.00000375",
        "cache_write_1h_token_price_usd": "0.000006",
        "price_source": "credits_api_static",
    },
    {
        "id": "anthropic/claude-haiku-4.5",
        "canonical_slug": "anthropic/claude-4.5-haiku-20251001",
        "display_name": "Anthropic: Claude Haiku 4.5",
        "prompt_token_price_usd": "0.000001",
        "completion_token_price_usd": "0.000005",
        "cache_read_token_price_usd": "0.0000001",
        "cache_write_token_price_usd": "0.00000125",
        "cache_write_5m_token_price_usd": "0.00000125",
        "cache_write_1h_token_price_usd": "0.000002",
        "price_source": "credits_api_static",
    },
    {
        "id": "anthropic/claude-3.5-haiku",
        "canonical_slug": "anthropic/claude-3.5-haiku",
        "display_name": "Anthropic: Claude 3.5 Haiku",
        "prompt_token_price_usd": "0.0000008",
        "completion_token_price_usd": "0.000004",
        "cache_read_token_price_usd": "0.00000008",
        "cache_write_token_price_usd": "0.000001",
        "cache_write_5m_token_price_usd": "0.000001",
        "cache_write_1h_token_price_usd": "0.0000016",
        "price_source": "legacy_static",
    },
    {
        "id": "openai/gpt-5.5",
        "canonical_slug": "openai/gpt-5.5-20260423",
        "display_name": "OpenAI: GPT-5.5",
        "prompt_token_price_usd": "0.000005",
        "completion_token_price_usd": "0.00003",
        "cache_read_token_price_usd": "0.0000005",
        "cache_write_token_price_usd": None,
        "price_source": "credits_api_static",
    },
    {
        "id": "openai/gpt-5.4",
        "canonical_slug": "openai/gpt-5.4-20260305",
        "display_name": "OpenAI: GPT-5.4",
        "prompt_token_price_usd": "0.0000025",
        "completion_token_price_usd": "0.000015",
        "cache_read_token_price_usd": "0.00000025",
        "cache_write_token_price_usd": None,
        "price_source": "credits_api_static",
    },
    {
        "id": "openai/gpt-5.4-mini",
        "canonical_slug": "openai/gpt-5.4-mini-20260317",
        "display_name": "OpenAI: GPT-5.4 Mini",
        "prompt_token_price_usd": "0.00000075",
        "completion_token_price_usd": "0.0000045",
        "cache_read_token_price_usd": "0.000000075",
        "cache_write_token_price_usd": None,
        "price_source": "credits_api_static",
    },
    {
        "id": "openai/gpt-5-codex",
        "canonical_slug": "openai/gpt-5-codex",
        "display_name": "OpenAI: GPT-5 Codex",
        "prompt_token_price_usd": "0.00000125",
        "completion_token_price_usd": "0.00001",
        "cache_read_token_price_usd": "0.000000125",
        "cache_write_token_price_usd": None,
        "price_source": "credits_api_static",
    },
    {
        "id": "openai/gpt-5-mini",
        "canonical_slug": "openai/gpt-5-mini-2025-08-07",
        "display_name": "OpenAI: GPT-5 Mini",
        "prompt_token_price_usd": "0.00000025",
        "completion_token_price_usd": "0.000002",
        "cache_read_token_price_usd": "0.000000025",
        "cache_write_token_price_usd": None,
        "price_source": "credits_api_static",
    },
    {
        "id": "openai/gpt-5-nano",
        "canonical_slug": "openai/gpt-5-nano-2025-08-07",
        "display_name": "OpenAI: GPT-5 Nano",
        "prompt_token_price_usd": "0.00000005",
        "completion_token_price_usd": "0.0000004",
        "cache_read_token_price_usd": "0.000000005",
        "cache_write_token_price_usd": None,
        "price_source": "credits_api_static",
    },
    {
        "id": "openai/gpt-5.1-codex-mini",
        "canonical_slug": "openai/gpt-5.1-codex-mini-20251113",
        "display_name": "OpenAI: GPT-5.1 Codex Mini",
        "prompt_token_price_usd": "0.00000025",
        "completion_token_price_usd": "0.000002",
        "cache_read_token_price_usd": "0.000000025",
        "cache_write_token_price_usd": None,
        "price_source": "credits_api_static",
    },
]


def normalize_model_name(value):
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
        item = normalize_model_name(candidate)
        if item and item not in normalized:
            normalized.append(item)
    return set(normalized)


def create_catalog_entry(entry):
    entry_id = entry.get("id")
    if not entry_id:
        return None

    normalized_names = set()
    normalized_names.update(build_normalized_model_names(entry_id))
    normalized_names.update(build_normalized_model_names(entry.get("canonical_slug")))
    normalized_names.update(build_normalized_model_names(entry.get("display_name")))

    return {
        "id": entry_id,
        "canonical_slug": entry.get("canonical_slug"),
        "display_name": entry.get("display_name"),
        "normalized_names": normalized_names,
        "prompt_token_price_usd": entry.get("prompt_token_price_usd"),
        "completion_token_price_usd": entry.get("completion_token_price_usd"),
        "cache_read_token_price_usd": entry.get("cache_read_token_price_usd"),
        "cache_write_token_price_usd": entry.get("cache_write_token_price_usd"),
        "cache_write_5m_token_price_usd": entry.get("cache_write_5m_token_price_usd"),
        "cache_write_1h_token_price_usd": entry.get("cache_write_1h_token_price_usd"),
        "price_source": entry.get("price_source"),
    }


def build_pricing_catalog():
    entries = []
    for entry in FIXED_PRICING_TABLE:
        created = create_catalog_entry(entry)
        if created:
            entries.append(created)
    return {"entries": entries}


def get_pricing_catalog(force_refresh=False):
    global _PRICING_CATALOG
    if force_refresh or _PRICING_CATALOG is None:
        _PRICING_CATALOG = build_pricing_catalog()
    return _PRICING_CATALOG


def match_pricing_model(model_id, catalog=None):
    catalog = catalog or get_pricing_catalog()
    normalized_names = build_normalized_model_names(model_id)
    if not normalized_names:
        return None

    exact_matches = []
    for entry in catalog.get("entries", []):
        if entry["normalized_names"] & normalized_names and entry not in exact_matches:
            exact_matches.append(entry)
    if len(exact_matches) == 1:
        return exact_matches[0]

    prefix_matches = []
    for entry in catalog.get("entries", []):
        if any(
            query.startswith(candidate) or candidate.startswith(query)
            for candidate in entry["normalized_names"]
            for query in normalized_names
        ) and entry not in prefix_matches:
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


def select_price(entry, price_key):
    price = entry.get(price_key)
    if price is None:
        return None
    return Decimal(str(price))


def calculate_estimated_cost(
    model_id,
    input_tokens=0,
    output_tokens=0,
    cache_read_tokens=0,
    cache_write_tokens=0,
    cache_write_5m_tokens=0,
    cache_write_1h_tokens=0,
    catalog=None,
):
    entry = match_pricing_model(model_id, catalog=catalog)
    if not entry:
        return None, None

    parts = [
        cost_contribution(input_tokens, select_price(entry, "prompt_token_price_usd")),
        cost_contribution(output_tokens, select_price(entry, "completion_token_price_usd")),
        cost_contribution(cache_read_tokens, select_price(entry, "cache_read_token_price_usd")),
    ]

    if cache_write_5m_tokens or cache_write_1h_tokens:
        parts.extend(
            [
                cost_contribution(
                    cache_write_5m_tokens,
                    select_price(entry, "cache_write_5m_token_price_usd"),
                ),
                cost_contribution(
                    cache_write_1h_tokens,
                    select_price(entry, "cache_write_1h_token_price_usd"),
                ),
            ]
        )
    else:
        parts.append(cost_contribution(cache_write_tokens, select_price(entry, "cache_write_token_price_usd")))

    if any(part is None for part in parts):
        return entry, None
    return entry, sum(parts, Decimal("0"))
