import unittest

import openrouter_pricing as p


class OpenRouterPricingTest(unittest.TestCase):
    def test_match_openrouter_model_uses_normalized_names(self):
        snapshot = {
            "entries": [
                p.create_entry(
                    {
                        "id": "anthropic/claude-sonnet-4.6",
                        "canonical_slug": "anthropic/claude-4.6-sonnet-20260217",
                        "display_name": "Anthropic: Claude Sonnet 4.6",
                        "prompt_token_price_usd": "0.000003",
                        "completion_token_price_usd": "0.000015",
                        "cache_read_token_price_usd": "0.0000003",
                        "cache_write_token_price_usd": "0.00000375",
                    }
                )
            ]
        }

        entry = p.match_openrouter_model("claude-sonnet-4-6", snapshot=snapshot)

        self.assertIsNotNone(entry)
        self.assertEqual(entry["id"], "anthropic/claude-sonnet-4.6")

    def test_calculate_estimated_cost_uses_usd_per_token_directly(self):
        snapshot = {
            "entries": [
                p.create_entry(
                    {
                        "id": "openai/gpt-5-mini",
                        "canonical_slug": "openai/gpt-5-mini-2025-08-07",
                        "display_name": "OpenAI: GPT-5 Mini",
                        "prompt_token_price_usd": "0.00000025",
                        "completion_token_price_usd": "0.000002",
                        "cache_read_token_price_usd": "0.000000025",
                        "cache_write_token_price_usd": None,
                    }
                )
            ]
        }

        _entry, cost = p.calculate_estimated_cost(
            "gpt-5-mini",
            input_tokens=100,
            output_tokens=5,
            cache_read_tokens=20,
            snapshot=snapshot,
        )

        self.assertAlmostEqual(cost, 100 * 0.00000025 + 5 * 0.000002 + 20 * 0.000000025)

    def test_calculate_estimated_cost_uses_api_override_cache_write_1h_without_deprecated_long_context_multiplier(self):
        snapshot = {
            "entries": [
                p.create_entry(
                    {
                        "id": "anthropic/claude-sonnet-4.5",
                        "canonical_slug": "anthropic/claude-4.5-sonnet-20250929",
                        "display_name": "Anthropic: Claude Sonnet 4.5",
                        "prompt_token_price_usd": "0.000003",
                        "completion_token_price_usd": "0.000015",
                        "cache_read_token_price_usd": "0.0000003",
                        "cache_write_token_price_usd": "0.00000375",
                    }
                )
            ]
        }

        _entry, short_cost = p.calculate_estimated_cost(
            "claude-sonnet-4-5",
            input_tokens=200000,
            cache_read_tokens=200000,
            cache_write_5m_tokens=200000,
            cache_write_1h_tokens=200000,
            snapshot=snapshot,
        )
        _entry, long_cost = p.calculate_estimated_cost(
            "claude-sonnet-4-5",
            input_tokens=200001,
            cache_read_tokens=200001,
            cache_write_5m_tokens=200001,
            cache_write_1h_tokens=200001,
            snapshot=snapshot,
        )

        self.assertAlmostEqual(short_cost, 200000 * (0.000003 + 0.0000003 + 0.00000375 + 0.000006))
        self.assertAlmostEqual(long_cost, 200001 * (0.000003 + 0.0000003 + 0.00000375 + 0.000006))

    def test_resolve_catalog_uses_static_api_catalog_for_supported_models(self):
        p._CATALOG_CACHE = None
        snapshot = p.resolve_catalog(force_refresh=True)
        entry = next(item for item in snapshot["entries"] if item["id"] == "openai/gpt-5.4")
        self.assertEqual(entry["pricing_source"], "credits_api")
        self.assertEqual(entry["prompt_token_price_usd"], "0.0000025")

    def test_resolve_catalog_keeps_local_fallback_models_missing_from_api(self):
        p._CATALOG_CACHE = None

        snapshot = p.resolve_catalog(force_refresh=True)
        entry = p.match_openrouter_model("claude-fable-5", snapshot=snapshot)

        self.assertIsNotNone(entry)
        self.assertEqual(entry["id"], "anthropic/claude-fable-5")
        self.assertEqual(entry["pricing_source"], "legacy_static")

    def test_resolve_catalog_marks_newly_supported_models_as_credits_api(self):
        p._CATALOG_CACHE = None

        snapshot = p.resolve_catalog(force_refresh=True)
        opus_entry = p.match_openrouter_model("claude-opus-4.1", snapshot=snapshot)
        codex_entry = p.match_openrouter_model("gpt-5.1-codex-mini", snapshot=snapshot)

        self.assertIsNotNone(opus_entry)
        self.assertEqual(opus_entry["pricing_source"], "credits_api")
        self.assertEqual(opus_entry["cache_write_1h_token_price_usd"], "0.00003")
        self.assertIsNotNone(codex_entry)
        self.assertEqual(codex_entry["pricing_source"], "credits_api")
        self.assertEqual(codex_entry["prompt_token_price_usd"], "0.00000025")


if __name__ == "__main__":
    unittest.main()