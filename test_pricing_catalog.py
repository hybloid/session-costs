import unittest
from decimal import Decimal

import pricing_catalog as p


class PricingCatalogTest(unittest.TestCase):
    def test_match_pricing_model_uses_normalized_names(self):
        snapshot = {
            "entries": [
                p.create_catalog_entry(
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

        entry = p.match_pricing_model("claude-sonnet-4-6", catalog=snapshot)

        self.assertIsNotNone(entry)
        self.assertEqual(entry["id"], "anthropic/claude-sonnet-4.6")

    def test_calculate_estimated_cost_counts_cached_reads(self):
        snapshot = {
            "entries": [
                p.create_catalog_entry(
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
            catalog=snapshot,
        )

        self.assertIsInstance(cost, Decimal)
        self.assertEqual(cost, Decimal("0.000035500"))

    def test_calculate_estimated_cost_uses_explicit_hourly_cache_write_price(self):
        snapshot = {
            "entries": [
                p.create_catalog_entry(
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
                    }
                )
            ]
        }

        _entry, short_cost = p.calculate_estimated_cost(
            "claude-sonnet-4.5",
            input_tokens=200000,
            cache_read_tokens=200000,
            cache_write_5m_tokens=200000,
            cache_write_1h_tokens=200000,
            catalog=snapshot,
        )
        _entry, long_cost = p.calculate_estimated_cost(
            "claude-sonnet-4.5",
            input_tokens=200001,
            cache_read_tokens=200001,
            cache_write_5m_tokens=200001,
            cache_write_1h_tokens=200001,
            catalog=snapshot,
        )

        self.assertEqual(short_cost, Decimal("2.61"))
        self.assertEqual(long_cost, Decimal("2.61001305"))

    def test_get_pricing_catalog_uses_static_table_for_api_backed_models(self):
        p._PRICING_CATALOG = None
        snapshot = p.get_pricing_catalog(force_refresh=True)
        entry = next(item for item in snapshot["entries"] if item["id"] == "openai/gpt-5.4")
        self.assertEqual(entry["price_source"], "credits_api_static")
        self.assertEqual(entry["prompt_token_price_usd"], "0.0000025")

    def test_get_pricing_catalog_keeps_legacy_static_models(self):
        p._PRICING_CATALOG = None

        snapshot = p.get_pricing_catalog(force_refresh=True)
        entry = p.match_pricing_model("claude-fable-5", catalog=snapshot)

        self.assertIsNotNone(entry)
        self.assertEqual(entry["id"], "anthropic/claude-fable-5")
        self.assertEqual(entry["price_source"], "legacy_static")

    def test_get_pricing_catalog_marks_newly_supported_models_as_api_static(self):
        p._PRICING_CATALOG = None

        snapshot = p.get_pricing_catalog(force_refresh=True)
        opus_entry = p.match_pricing_model("claude-opus-4.1", catalog=snapshot)
        codex_entry = p.match_pricing_model("gpt-5.1-codex-mini", catalog=snapshot)

        self.assertIsNotNone(opus_entry)
        self.assertEqual(opus_entry["price_source"], "credits_api_static")
        self.assertEqual(opus_entry["cache_write_1h_token_price_usd"], "0.00003")
        self.assertIsNotNone(codex_entry)
        self.assertEqual(codex_entry["price_source"], "credits_api_static")
        self.assertEqual(codex_entry["prompt_token_price_usd"], "0.00000025")


if __name__ == "__main__":
    unittest.main()
