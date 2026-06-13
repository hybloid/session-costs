import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import codex_costs_common as c
import openrouter_pricing as p
import codex_costs_conservative as conservative


class CodexCostsCommonTest(unittest.TestCase):
    def write_rollout(self, day_dir, name, records):
        path = day_dir / name
        with path.open("w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        return path

    def test_collect_entries_rolls_subagent_into_root_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_dir = root / "sessions" / "2026" / "06" / "12"
            sessions_dir.mkdir(parents=True)
            history_path = root / "history.jsonl"
            history_path.write_text(
                json.dumps({"session_id": "root-session", "text": "Main Codex task"}) + "\n"
            )

            self.write_rollout(
                sessions_dir,
                "rollout-root-session.jsonl",
                [
                    {
                        "timestamp": "2026-06-12T10:00:00Z",
                        "event_msg": {
                            "type": "session_meta",
                            "payload": {"id": "root-session", "model": "gpt-5.4", "cwd": "/tmp/project"},
                        },
                    },
                    {
                        "timestamp": "2026-06-12T10:01:00Z",
                        "event_msg": {
                            "type": "token_count",
                            "payload": {
                                "turn_id": "turn-root",
                                "info": {
                                    "total_token_usage": {
                                        "input_tokens": 100,
                                        "cached_input_tokens": 20,
                                        "output_tokens": 50,
                                        "reasoning_output_tokens": 30,
                                        "total_tokens": 150,
                                    }
                                },
                            },
                        },
                    },
                ],
            )

            self.write_rollout(
                sessions_dir,
                "rollout-sub-session.jsonl",
                [
                    {
                        "timestamp": "2026-06-12T10:02:00Z",
                        "event_msg": {
                            "type": "session_meta",
                            "payload": {
                                "id": "sub-session",
                                "model": "gpt-5-mini",
                                "source": {"subagent": {"thread_spawn": {"parent_thread_id": "root-session"}}},
                            },
                        },
                    },
                    {
                        "timestamp": "2026-06-12T10:03:00Z",
                        "event_msg": {
                            "type": "token_count",
                            "payload": {
                                "turn_id": "turn-sub",
                                "info": {
                                    "total_token_usage": {
                                        "input_tokens": 40,
                                        "cached_input_tokens": 5,
                                        "output_tokens": 10,
                                        "reasoning_output_tokens": 4,
                                        "total_tokens": 50,
                                    }
                                },
                            },
                        },
                    },
                ],
            )

            with mock.patch.object(c, "CODEX_SESSIONS_ROOT", root / "sessions"), mock.patch.object(
                c, "CODEX_HISTORY_PATH", history_path
            ):
                entries, display_names = c.collect_entries(date(2026, 6, 12))

            self.assertEqual(len(entries), 2)
            self.assertEqual({entry["session_id"] for entry in entries}, {"root-session"})
            self.assertEqual(display_names["root-session"], "Main Codex task")

    def test_conservative_uses_max_total_snapshot_per_turn(self):
        entries = [
            {
                "session_id": "root-session",
                "leaf_session_id": "root-session",
                "snapshot_id": "turn-1",
                "usage": {"in": 100, "out": 40, "c_read": 20, "reasoning": 10},
                "model": "gpt-5.4",
            },
            {
                "session_id": "root-session",
                "leaf_session_id": "root-session",
                "snapshot_id": "turn-1",
                "usage": {"in": 120, "out": 50, "c_read": 30, "reasoning": 12},
                "model": "gpt-5.4",
            },
            {
                "session_id": "root-session",
                "leaf_session_id": "sub-session",
                "snapshot_id": "turn-2",
                "usage": {"in": 10, "out": 5, "c_read": 4, "reasoning": 2},
                "model": "gpt-5-mini",
            },
        ]

        snapshot = {
            "entries": [
                p.create_entry(
                    {
                        "id": "openai/gpt-5.4",
                        "canonical_slug": "openai/gpt-5.4-20260305",
                        "display_name": "OpenAI: GPT-5.4",
                        "prompt_token_price_usd": "0.0000025",
                        "completion_token_price_usd": "0.000015",
                        "cache_read_token_price_usd": "0.00000025",
                        "cache_write_token_price_usd": None,
                    }
                ),
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
                ),
            ]
        }

        with mock.patch.object(conservative, "resolve_catalog", return_value=snapshot):
            session_rows = conservative.aggregate_snapshot_max(entries)
        usage = session_rows["root-session"]["usage"]
        self.assertEqual(usage, {"in": 130, "out": 55, "c_read": 34, "reasoning": 14})

        expected_cost = (
            120 * 0.0000025
            + 50 * 0.000015
            + 30 * 0.00000025
            + 10 * 0.00000025
            + 5 * 0.000002
            + 4 * 0.000000025
        )
        self.assertAlmostEqual(session_rows["root-session"]["cost"], expected_cost)
        self.assertEqual(set(session_rows["root-session"]["models"].keys()), {"OpenAI: GPT-5.4", "OpenAI: GPT-5 Mini"})

    def test_collect_entries_filters_by_local_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_dir = root / "sessions" / "2026" / "06" / "12"
            sessions_dir.mkdir(parents=True)
            self.write_rollout(
                sessions_dir,
                "rollout-root-session.jsonl",
                [
                    {
                        "timestamp": "2026-06-12T10:00:00Z",
                        "event_msg": {"type": "session_meta", "payload": {"id": "root-session", "model": "gpt-5.4"}},
                    },
                    {
                        "timestamp": "2026-06-11T10:00:00Z",
                        "event_msg": {
                            "type": "token_count",
                            "payload": {
                                "turn_id": "turn-old",
                                "info": {"total_token_usage": {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 1}},
                            },
                        },
                    },
                    {
                        "timestamp": "2026-06-12T00:00:01Z",
                        "event_msg": {
                            "type": "token_count",
                            "payload": {
                                "turn_id": "turn-new",
                                "info": {"total_token_usage": {"input_tokens": 20, "cached_input_tokens": 5, "output_tokens": 2}},
                            },
                        },
                    },
                ],
            )

            with mock.patch.object(c, "CODEX_SESSIONS_ROOT", root / "sessions"), mock.patch.object(
                c, "CODEX_HISTORY_PATH", root / "history.jsonl"
            ):
                entries, _ = c.collect_entries(date(2026, 6, 12))

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["snapshot_id"], "turn-new")


if __name__ == "__main__":
    unittest.main()