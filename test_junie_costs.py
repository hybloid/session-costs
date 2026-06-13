import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import junie_costs as j


class JunieCostsTest(unittest.TestCase):
    def write_index(self, sessions_root, rows):
        path = sessions_root / "index.jsonl"
        with path.open("w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        return path

    def write_events(self, sessions_root, session_id, rows):
        session_dir = sessions_root / session_id
        session_dir.mkdir(parents=True)
        path = session_dir / "events.jsonl"
        with path.open("w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        return path

    def test_collect_entries_filters_by_local_date_and_session_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessions_root = Path(tmp) / "sessions"
            sessions_root.mkdir()
            index_path = self.write_index(
                sessions_root,
                [
                    {"sessionId": "session-a", "taskName": "Task A", "projectDir": "/tmp/project-a"},
                    {"sessionId": "session-b", "taskName": "Task B", "projectDir": "/tmp/project-b"},
                ],
            )
            self.write_events(
                sessions_root,
                "session-a",
                [
                    {
                        "timestampMs": 1781222401000,
                        "event": {"agentEvent": {"modelUsage": [{"model": "gpt-5.4", "cost": 1.25, "inputTokens": 100}]}}
                    },
                    {
                        "timestampMs": 1781136001000,
                        "event": {"agentEvent": {"modelUsage": [{"model": "gpt-5.4", "cost": 9.99, "inputTokens": 999}]}}
                    },
                ],
            )
            self.write_events(
                sessions_root,
                "session-b",
                [
                    {
                        "timestampMs": 1781222401000,
                        "event": {"agentEvent": {"modelUsage": [{"model": "gpt-4.1", "cost": 3.0, "inputTokens": 200}]}}
                    }
                ],
            )

            entries, session_index = j.collect_entries(
                target_date=date(2026, 6, 12),
                session_ids=["session-a"],
                sessions_root=sessions_root,
                index_path=index_path,
            )

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["session_id"], "session-a")
            self.assertEqual(entries[0]["cost"], 1.25)
            self.assertEqual(session_index["session-a"]["taskName"], "Task A")

    def test_collect_entries_accepts_all_time_and_multiple_model_usage_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessions_root = Path(tmp) / "sessions"
            sessions_root.mkdir()
            index_path = self.write_index(
                sessions_root,
                [{"sessionId": "session-a", "taskName": "Task A", "projectDir": "/tmp/project-a"}],
            )
            self.write_events(
                sessions_root,
                "session-a",
                [
                    {
                        "timestampMs": 1781136001000,
                        "event": {
                            "agentEvent": {
                                "modelUsage": [
                                    {"model": "gpt-5.4", "cost": 1.0, "inputTokens": 100, "cacheInputTokens": 10, "cacheCreateTokens": 5, "outputTokens": 20},
                                    {"model": "gpt-4.1-mini", "cost": 0.5, "inputTokens": 40, "cacheInputTokens": 0, "cacheCreateTokens": 0, "outputTokens": 5},
                                ]
                            }
                        },
                    }
                ],
            )

            entries, _ = j.collect_entries(target_date=None, sessions_root=sessions_root, index_path=index_path)

            self.assertEqual(len(entries), 2)
            self.assertEqual(sum(entry["cost"] for entry in entries), 1.5)
            self.assertEqual(sum(entry["c_read"] for entry in entries), 10)
            self.assertEqual(sum(entry["c_write"] for entry in entries), 5)

    def test_aggregate_entries_sums_costs_tokens_and_models(self):
        session_rows = j.aggregate_entries(
            [
                {
                    "session_id": "session-a",
                    "model": "gpt-5.4",
                    "cost": 1.0,
                    "in": 100,
                    "c_read": 10,
                    "c_write": 5,
                    "out": 20,
                },
                {
                    "session_id": "session-a",
                    "model": "gpt-4.1-mini",
                    "cost": 0.5,
                    "in": 40,
                    "c_read": 0,
                    "c_write": 0,
                    "out": 5,
                },
            ]
        )

        row = session_rows["session-a"]
        self.assertEqual(row["cost"], 1.5)
        self.assertEqual(row["calls"], 2)
        self.assertEqual(row["in"], 140)
        self.assertEqual(row["c_read"], 10)
        self.assertEqual(row["c_write"], 5)
        self.assertEqual(row["out"], 25)
        self.assertEqual(row["models"].most_common(1)[0][0], "gpt-5.4")

    def test_collect_entries_skips_sessions_outside_target_window_using_index_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessions_root = Path(tmp) / "sessions"
            sessions_root.mkdir()
            index_path = self.write_index(
                sessions_root,
                [
                    {
                        "sessionId": "session-old",
                        "taskName": "Old Task",
                        "projectDir": "/tmp/project-old",
                        "createdAt": 1779811200000,
                        "updatedAt": 1779897600000,
                    },
                    {
                        "sessionId": "session-current",
                        "taskName": "Current Task",
                        "projectDir": "/tmp/project-current",
                        "createdAt": 1781222400000,
                        "updatedAt": 1781226000000,
                    },
                ],
            )
            self.write_events(
                sessions_root,
                "session-old",
                [
                    {
                        "timestampMs": 1779811201000,
                        "event": {"agentEvent": {"modelUsage": [{"model": "gpt-5.4", "cost": 9.99, "inputTokens": 999}]}}
                    }
                ],
            )
            self.write_events(
                sessions_root,
                "session-current",
                [
                    {
                        "timestampMs": 1781222401000,
                        "event": {"agentEvent": {"modelUsage": [{"model": "gpt-5.4", "cost": 1.25, "inputTokens": 100}]}}
                    }
                ],
            )

            with mock.patch.object(j, "session_may_match_target_dates", wraps=j.session_may_match_target_dates) as filter_mock:
                entries, _ = j.collect_entries(
                    target_dates={date(2026, 6, 12)},
                    sessions_root=sessions_root,
                    index_path=index_path,
                )

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["session_id"], "session-current")
            self.assertEqual(filter_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()