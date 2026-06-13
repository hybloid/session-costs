import tempfile
import unittest
from pathlib import Path

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

    def test_resolve_catalog_uses_cached_snapshot_when_fresh(self):
        cached_entry = {
            "id": "openai/gpt-5.4",
            "canonical_slug": "openai/gpt-5.4-20260305",
            "display_name": "OpenAI: GPT-5.4",
            "prompt_token_price_usd": "0.0000025",
            "completion_token_price_usd": "0.000015",
            "cache_read_token_price_usd": "0.00000025",
            "cache_write_token_price_usd": None,
        }

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "catalog.json"
            p.save_snapshot({"fetched_at": 100, "entries": [p.create_entry(cached_entry)]}, cache_path=cache_path)
            p._CATALOG_CACHE = None

            snapshot = p.resolve_catalog(now=100 + p.CACHE_TTL_SECONDS - 1, cache_path=cache_path)

        self.assertEqual(snapshot["entries"][0]["id"], "openai/gpt-5.4")


if __name__ == "__main__":
    unittest.main()