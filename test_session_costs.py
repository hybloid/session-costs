import io
import json
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout
from decimal import Decimal
from datetime import date
from pathlib import Path

import session_costs as s


class SessionCostsTest(unittest.TestCase):
    def test_make_scope_info_for_week_and_month(self):
        week_scope = s.make_scope_info("week", date(2026, 6, 13))
        self.assertEqual(week_scope["start_date"], "2026-06-08")
        self.assertEqual(week_scope["end_date"], "2026-06-13")
        self.assertEqual(week_scope["dates"][0], "2026-06-08")
        self.assertEqual(week_scope["dates"][-1], "2026-06-13")

        month_scope = s.make_scope_info("month", date(2026, 6, 13))
        self.assertEqual(month_scope["start_date"], "2026-06-01")
        self.assertEqual(month_scope["end_date"], "2026-06-13")
        self.assertEqual(len(month_scope["dates"]), 13)

    def test_make_json_ready_removes_columns(self):
        report = {
            "scope": {"mode": "today"},
            "summary": [],
            "grand_total": {},
            "detailed_columns": [("name", "Name", "text")],
            "sources": [
                {
                    "label": "Claude",
                    "columns": [("name", "Name", "text")],
                    "rows": [{"name": "A"}],
                    "totals": {"cost_usd": Decimal("1.0")},
                }
            ],
        }

        json_ready = s.make_json_ready(report)
        self.assertNotIn("columns", json_ready["sources"][0])
        self.assertNotIn("detailed_columns", json_ready)
        self.assertEqual(json_ready["sources"][0]["rows"][0]["name"], "A")
        self.assertEqual(json_ready["sources"][0]["totals"]["cost_usd"], "1.0")

    def test_render_html_includes_summary_and_source_table(self):
        report = {
            "scope": {"mode": "today", "start_date": "2026-06-13", "end_date": "2026-06-13"},
            "summary": [{"source": "Claude", "sessions": 2, "calls": 0, "cost_usd": Decimal("12.5")}],
            "grand_total": {"sessions": 2, "calls": 0, "cost_usd": Decimal("12.5")},
            "groups": [
                {
                    "origin": "git@github.com:test/repo",
                    "totals": {"cost_usd": Decimal("12.5")},
                    "branches": [
                        {
                            "branch": "main",
                            "totals": {"cost_usd": Decimal("12.5")},
                            "locations": [
                                {
                                    "repository": "repo",
                                    "working_copy": "",
                                    "branch": "main",
                                    "totals": {"cost_usd": Decimal("12.5")},
                                    "rows": [{"name": "Test Dialogue", "agent": "Claude", "cost_usd": Decimal("12.5")}],
                                }
                            ],
                        }
                    ],
                }
            ],
            "detailed_columns": [
                ("name", "Dialogue", "text"),
                ("agent", "Agent", "text"),
                ("cost_usd", "Cost", "usd"),
            ],
            "sources": [
                {
                    "label": "Claude",
                    "columns": [
                        ("name", "Dialogue", "text"),
                        ("cost_usd", "Cost", "usd"),
                    ],
                    "rows": [{"name": "Test Dialogue", "cost_usd": Decimal("12.5")}],
                    "totals": {"cost_usd": Decimal("12.5")},
                }
            ],
        }

        html = s.render_html(report)
        self.assertIn("<h1>Session cost summary</h1>", html)
        self.assertIn(">Summary</h2>", html)
        self.assertIn("Detailed sessions", html)
        self.assertIn("Test Dialogue", html)
        self.assertIn("$12.500000", html)

    def test_render_text_table_truncates_long_text_columns(self):
        rows = [
            {
                "name": "This is a very long dialogue title that should not stretch the full terminal table across the screen",
                "models": "claude-opus-4.8-super-long-model-name",
                "cost_usd": Decimal("12.5"),
            }
        ]

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            s.render_text_table(
                "Claude",
                [
                    ("name", "Dialogue", "text"),
                    ("models", "Model", "text"),
                    ("cost_usd", "Cost", "usd"),
                ],
                rows,
                {"cost_usd": Decimal("12.5")},
            )

        rendered = buffer.getvalue()
        self.assertIn("…", rendered)
        self.assertIn("$12.500000", rendered)
        data_line = next(line for line in rendered.splitlines() if "$12.500000" in line and "TOTAL" not in line)
        self.assertLessEqual(len(data_line), 80)

    def test_render_text_table_collapses_multiline_dialogue_names(self):
        rows = [
            {
                "name": "1) скачай исходники zed\n2) найди описание утилиты\n3) проверь запуск",
                "models": "haiku",
                "cost_usd": Decimal("73.8218"),
            }
        ]

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            s.render_text_table(
                "Claude",
                [
                    ("name", "Dialogue", "text"),
                    ("models", "Model", "text"),
                    ("cost_usd", "Cost", "usd"),
                ],
                rows,
                {"cost_usd": Decimal("73.8218")},
            )

        rendered = buffer.getvalue()
        self.assertNotIn("\n2) найди описание утилиты", rendered)
        self.assertIn("1) скачай исходники zed 2) найди описание утили", rendered)
        self.assertIn("…", rendered)
        data_line = next(line for line in rendered.splitlines() if "$73.821800" in line and "TOTAL" not in line)
        self.assertEqual(data_line.count("|"), 2)

    def test_render_text_table_uses_terminal_width_consistently(self):
        rows = [
            {
                "name": "A very long dialogue title that should stretch to the available terminal width cleanly",
                "agent": "Claude",
                "models": "opus-4.8",
                "cost_usd": Decimal("12.5"),
            }
        ]

        buffer = io.StringIO()
        with mock.patch.object(s.shutil, "get_terminal_size", return_value=mock.Mock(columns=72)), redirect_stdout(buffer):
            s.render_text_table(
                "Claude",
                [
                    ("name", "Dialogue", "text"),
                    ("agent", "Agent", "text"),
                    ("models", "Model", "text"),
                    ("cost_usd", "Cost", "usd"),
                ],
                rows,
                {"cost_usd": Decimal("12.5")},
                indent="    ",
            )

        lines = [line for line in buffer.getvalue().splitlines() if "|" in line or "+" in line]
        self.assertTrue(lines)
        self.assertTrue(all(len(line) == 72 for line in lines))

    def test_classify_project_path_handles_worktrees_and_working_copies(self):
        with mock.patch.object(s, "resolve_git_metadata", return_value={"origin": "git@github.com:acme/chatter", "branch": "sunny-veranda"}):
            worktree = s.classify_project_path("/home/alex/dev/worktrees/chatter/sunny-veranda/chatter")
        self.assertEqual(worktree["repository"], "chatter")
        self.assertEqual(worktree["working_copy"], "sunny-veranda")
        self.assertEqual(worktree["branch"], "sunny-veranda")
        self.assertEqual(worktree["origin"], "git@github.com:acme/chatter")

        with mock.patch.object(s, "resolve_git_metadata", return_value={"origin": "ssh://git.example.com/acme/ultimate", "branch": "feature/x"}):
            working_copy = s.classify_project_path("/workspace/ultimate-2")
        self.assertEqual(working_copy["repository"], "ultimate")
        self.assertEqual(working_copy["working_copy"], "ultimate-2")
        self.assertEqual(working_copy["branch"], "feature/x")
        self.assertEqual(working_copy["origin"], "ssh://git.example.com/acme/ultimate")

    def test_infer_claude_location_from_rollout_path_handles_encoded_worktree(self):
        location = s.infer_claude_location_from_rollout_path(
            "/home/alex/.claude/projects/-home-alex-dev-worktrees-public-tools-sunny-branch-public-tools/"
            "ee559b79-0afa-40fd-9576-0ef9da806ec8.jsonl"
        )

        self.assertEqual(location["repository"], "public-tools")
        self.assertEqual(location["working_copy"], "sunny-branch")
        self.assertEqual(location["branch"], "sunny-branch")

    def test_build_source_groups_groups_rows_by_origin_then_branch(self):
        rows = [
            {
                "name": "A",
                "origin": "git@github.com:acme/public-tools",
                "repository": "public-tools",
                "working_copy": "",
                "branch": "",
                "calls": 0,
                "input_tokens": 10,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "cache_write_5m_tokens": 0,
                "cache_write_1h_tokens": 0,
                "output_tokens": 5,
                "reasoning_tokens": 0,
                "cost_usd": Decimal("1.0"),
            },
            {
                "name": "B",
                "origin": "git@github.com:acme/public-tools",
                "repository": "public-tools",
                "working_copy": "sunny-branch",
                "branch": "sunny-branch",
                "calls": 0,
                "input_tokens": 20,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "cache_write_5m_tokens": 0,
                "cache_write_1h_tokens": 0,
                "output_tokens": 15,
                "reasoning_tokens": 0,
                "cost_usd": Decimal("2.5"),
            },
        ]

        groups = s.build_source_groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["origin"], "git@github.com:acme/public-tools")
        self.assertEqual(groups[0]["totals"]["cost_usd"], Decimal("3.5"))
        self.assertEqual(len(groups[0]["branches"]), 2)
        self.assertEqual(groups[0]["branches"][0]["branch"], "sunny-branch")
        self.assertEqual(groups[0]["branches"][0]["totals"]["cost_usd"], Decimal("2.5"))
        self.assertEqual(groups[0]["branches"][0]["locations"][0]["working_copy"], "sunny-branch")
        self.assertEqual(groups[0]["branches"][1]["branch"], "")
        self.assertEqual(groups[0]["branches"][1]["locations"][0]["repository"], "public-tools")

    def test_with_optional_agent_column_adds_field_without_grouping(self):
        columns = [("name", "Dialogue", "text"), ("cost_usd", "Cost", "usd")]
        rows = [{"name": "A", "agent": "subagent", "cost_usd": Decimal("1.0")}]

        with_agent = s.with_optional_agent_column(columns, rows)
        self.assertEqual(with_agent[1], ("agent", "Agent", "text"))

        without_agent = s.with_optional_agent_column(columns, [{"name": "A", "agent": "", "cost_usd": Decimal("1.0")}])
        self.assertEqual(without_agent, columns)

    def test_collect_codex_report_prefers_internal_display_and_shows_agent_column(self):
        entries = [
            {
                "session_id": "root-1",
                "leaf_session_id": "leaf-1",
                "snapshot_id": "snap-1",
                "timestamp": None,
                "usage": {"in": 10, "out": 5, "c_read": 2, "reasoning": 1},
                "model": "gpt-5.5",
                "agent": "reviewer",
                "project_path": "/tmp/sample-repo",
            }
        ]
        session_rows = {
            "root-1": {
                "usage": {"in": 10, "out": 5, "c_read": 2, "reasoning": 1},
                "models": {"gpt-5.5": {}},
                "cost": Decimal("12.34"),
            }
        }

        with mock.patch.object(s.codex_common, "collect_entries", return_value=(entries, {"root-1": "Investigate startup flow"})), \
             mock.patch.object(s, "aggregate_snapshot_max", return_value=session_rows), \
             mock.patch.object(s, "resolve_git_metadata", return_value={"origin": "git@github.com:acme/sample-repo", "branch": "main"}):
            report = s.collect_codex_report({date(2026, 6, 13)})

        self.assertEqual(report["rows"][0]["name"], "Investigate startup flow")
        self.assertEqual(report["rows"][0]["agent"], "Codex")
        self.assertIn(("agent", "Agent", "text"), report["columns"])

    def test_collect_claude_report_sets_provider_as_agent(self):
        entries = [
            {"session_id": "sess-1", "path": "/tmp/.claude/projects/repo/sess-1.jsonl"},
            {"session_id": "sess-1", "path": "/tmp/.claude/projects/repo/sess-1/subagents/agent-reviewer.jsonl"},
            {"session_id": "sess-1", "path": "/tmp/.claude/projects/repo/sess-1/subagents/agent-planner.jsonl"},
        ]
        session_rows = {
            "sess-1": {
                "model": "sonnet",
                "in": 100,
                "c_read": 50,
                "c_write_5m": 10,
                "c_write_1h": 0,
                "out": 25,
                "cost": Decimal("1.5"),
            }
        }

        with mock.patch.object(s.claude_common, "collect_entries", return_value=(entries, {"sess-1": "Dialog"})), \
             mock.patch.object(s, "aggregate_message_max", return_value=session_rows), \
             mock.patch.object(s, "load_claude_session_projects", return_value={}), \
             mock.patch.object(s, "resolve_git_metadata", return_value={}):
            report = s.collect_claude_report({date(2026, 6, 13)})

        self.assertEqual(report["rows"][0]["agent"], "Claude")
        self.assertIn(("agent", "Agent", "text"), report["columns"])

    def test_render_console_uses_indentation_for_grouped_sections(self):
        report = {
            "scope": {"mode": "today", "start_date": "2026-06-13", "end_date": "2026-06-13"},
            "summary": [{"source": "Codex", "sessions": 1, "calls": 0, "cost_usd": Decimal("12.5")}],
            "grand_total": {"sessions": 1, "calls": 0, "cost_usd": Decimal("12.5")},
            "groups": [
                {
                    "origin": "git@github.com:acme/sample-repo",
                    "totals": {"cost_usd": Decimal("12.5")},
                    "branches": [
                        {
                            "branch": "main",
                            "totals": {"cost_usd": Decimal("12.5")},
                            "locations": [
                                {
                                    "repository": "sample-repo",
                                    "working_copy": "",
                                    "branch": "main",
                                    "totals": {"cost_usd": Decimal("12.5")},
                                    "rows": [{"name": "Task", "agent": "Codex", "cost_usd": Decimal("12.5")}],
                                }
                            ],
                        }
                    ],
                }
            ],
            "detailed_columns": [("name", "Dialogue", "text"), ("agent", "Agent", "text"), ("cost_usd", "Cost", "usd")],
            "sources": [
                {
                    "label": "Codex",
                    "columns": [("name", "Dialogue", "text"), ("agent", "Agent", "text"), ("cost_usd", "Cost", "usd")],
                    "rows": [{"name": "Task", "agent": "Codex", "cost_usd": Decimal("12.5")}],
                    "totals": {"cost_usd": Decimal("12.5")},
                    "groups": [
                        {
                            "origin": "git@github.com:acme/sample-repo",
                            "totals": {"cost_usd": Decimal("12.5")},
                            "branches": [
                                {
                                    "branch": "main",
                                    "totals": {"cost_usd": Decimal("12.5")},
                                    "locations": [
                                        {
                                            "repository": "sample-repo",
                                            "working_copy": "",
                                            "branch": "main",
                                            "totals": {"cost_usd": Decimal("12.5")},
                                            "rows": [{"name": "Task", "agent": "Codex", "cost_usd": Decimal("12.5")}],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            s.render_console(report)

        rendered = buffer.getvalue()
        self.assertIn("Origin: git@github.com:acme/sample-repo", rendered)
        self.assertIn("  Branch: main", rendered)
        self.assertIn("    Repository: sample-repo", rendered)
        self.assertNotIn("\nCodex\n", rendered)

    def test_build_report_creates_unified_groups_without_provider_sections(self):
        claude_report = {
            "source": "claude",
            "label": "Claude",
            "columns": [("name", "Dialogue", "text")],
            "groups": [],
            "rows": [{"name": "Claude task", "agent": "Claude", "repository": "repo", "working_copy": "", "branch": "main", "origin": "origin/repo", "cost_usd": Decimal("5.0")}],
            "totals": {**s.source_totals_template(), "sessions": 1, "cost_usd": Decimal("5.0")},
        }
        codex_report = {
            "source": "codex",
            "label": "Codex",
            "columns": [("name", "Dialogue", "text")],
            "groups": [],
            "rows": [{"name": "Codex task", "agent": "Codex", "repository": "repo", "working_copy": "", "branch": "main", "origin": "origin/repo", "cost_usd": Decimal("7.0")}],
            "totals": {**s.source_totals_template(), "sessions": 1, "cost_usd": Decimal("7.0")},
        }
        junie_report = {
            "source": "junie",
            "label": "Junie",
            "columns": [("name", "Task", "text")],
            "groups": [],
            "rows": [{"name": "Junie task", "agent": "Junie", "repository": "repo", "working_copy": "", "branch": "main", "origin": "origin/repo", "cost_usd": Decimal("2.0")}],
            "totals": {**s.source_totals_template(), "sessions": 1, "cost_usd": Decimal("2.0")},
        }

        with mock.patch.object(s, "collect_claude_report", return_value=claude_report), \
             mock.patch.object(s, "collect_codex_report", return_value=codex_report), \
             mock.patch.object(s, "collect_junie_report", return_value=junie_report):
            report = s.build_report("today", date(2026, 6, 13))

        self.assertEqual([row[1] for row in report["detailed_columns"]], ["Dialogue", "Agent", "Model", "Cost"])
        self.assertEqual(report["groups"][0]["origin"], "origin/repo")
        rows = report["groups"][0]["branches"][0]["locations"][0]["rows"]
        self.assertEqual([row["agent"] for row in rows], ["Codex", "Claude", "Junie"])

    def test_build_report_can_enable_expanded_detailed_columns(self):
        claude_report = {
            "source": "claude",
            "label": "Claude",
            "columns": [("name", "Dialogue", "text")],
            "groups": [],
            "rows": [{"name": "Claude task", "agent": "Claude", "models": "opus", "repository": "repo", "working_copy": "", "branch": "main", "origin": "origin/repo", "cost_usd": Decimal("5.0")}],
            "totals": {**s.source_totals_template(), "sessions": 1, "cost_usd": Decimal("5.0")},
        }

        with mock.patch.object(s, "collect_claude_report", return_value=claude_report), \
             mock.patch.object(s, "collect_codex_report", return_value={"source": "codex", "label": "Codex", "columns": [], "groups": [], "rows": [], "totals": s.source_totals_template()}), \
             mock.patch.object(s, "collect_junie_report", return_value={"source": "junie", "label": "Junie", "columns": [], "groups": [], "rows": [], "totals": s.source_totals_template()}):
            report = s.build_report("today", date(2026, 6, 13), detailed=True)

        self.assertEqual([row[1] for row in report["detailed_columns"][:6]], ["Dialogue", "Agent", "Model", "Calls", "In (MT)", "Cached"])

    def test_main_can_write_html_and_emit_json(self):
        fake_report = {
            "generated_at": "2026-06-13T15:00:00+03:00",
            "scope": {"mode": "today", "start_date": "2026-06-13", "end_date": "2026-06-13"},
            "summary": [{"source": "Claude", "sessions": 1, "calls": 0, "cost_usd": Decimal("1.25")}],
            "grand_total": {"sessions": 1, "calls": 0, "cost_usd": Decimal("1.25")},
            "sources": [
                {
                    "label": "Claude",
                    "columns": [("name", "Dialogue", "text")],
                    "rows": [{"name": "Dialog"}],
                    "totals": {"cost_usd": Decimal("1.25")},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "report.html"
            with mock.patch.object(s, "build_report", return_value=fake_report) as build_report_mock, mock.patch(
                "sys.argv",
                ["session_costs.py", "--json", "--html", str(html_path), "--detailed"],
            ), mock.patch("sys.stdout") as stdout:
                s.main()

            rendered = "".join(call.args[0] for call in stdout.write.call_args_list)
            payload = json.loads(rendered)
            self.assertEqual(payload["summary"][0]["source"], "Claude")
            build_report_mock.assert_called_once_with("today", date.today(), detailed=True)
            self.assertTrue(html_path.exists())
            self.assertIn("Session cost summary", html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()