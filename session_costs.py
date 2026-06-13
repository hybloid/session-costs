#!/usr/bin/env python3
import argparse
import subprocess
import json
import re
import shutil
from decimal import Decimal
from functools import lru_cache
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

import claude_costs_common as claude_common
import codex_costs_common as codex_common
from claude_costs_conservative import aggregate_message_max
from codex_costs_conservative import aggregate_snapshot_max
from junie_costs import aggregate_entries as aggregate_junie_entries
from junie_costs import collect_entries as collect_junie_entries
from junie_costs import format_models as format_junie_models
from junie_costs import short_project_name

CLAUDE_HISTORY_PATH = Path("~/.claude/history.jsonl").expanduser()
WORKING_COPY_SUFFIX_RE = re.compile(r"^(?P<repo>.+)-(?P<copy>\d+)$")
ZERO_USD = Decimal("0")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scope",
        choices=["today", "week", "month"],
        default="today",
        help="today = anchor date, week = current calendar week, month = current month from day 1",
    )
    parser.add_argument("--date", help="Anchor date in YYYY-MM-DD format. Defaults to local today.")
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON to stdout.")
    parser.add_argument("--summary", action="store_true", help="Show only the cross-source summary table in text/HTML output.")
    parser.add_argument("--detailed", action="store_true", help="Show expanded per-session metrics in the detailed table.")
    parser.add_argument("--html", help="Write a simple HTML report to this file path.")
    return parser.parse_args()


def resolve_anchor_date(raw_date):
    if not raw_date:
        return date.today()
    return date.fromisoformat(raw_date)


def resolve_scope_window(scope, anchor_date):
    if scope == "today":
        start_date = anchor_date
    elif scope == "week":
        start_date = anchor_date - timedelta(days=anchor_date.weekday())
    else:
        start_date = anchor_date.replace(day=1)
    return start_date, anchor_date


def iter_dates(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def make_scope_info(scope, anchor_date):
    start_date, end_date = resolve_scope_window(scope, anchor_date)
    dates = list(iter_dates(start_date, end_date))
    return {
        "mode": scope,
        "anchor_date": anchor_date.isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "dates": [item.isoformat() for item in dates],
        "target_dates": set(dates),
    }


def source_totals_template():
    return {
        "sessions": 0,
        "calls": 0,
        "input_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cache_write_5m_tokens": 0,
        "cache_write_1h_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": ZERO_USD,
    }


TOTAL_KEYS = tuple(source_totals_template().keys())


def add_totals(target, values):
    for key in TOTAL_KEYS:
        if key == "cost_usd":
            target[key] += values.get(key, ZERO_USD) or ZERO_USD
        else:
            target[key] += values.get(key, 0) or 0


def load_claude_session_projects():
    projects = {}
    if not CLAUDE_HISTORY_PATH.exists():
        return projects

    with CLAUDE_HISTORY_PATH.open() as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            session_id = record.get("sessionId")
            project = record.get("project")
            if session_id and project:
                projects[session_id] = project

    return projects


def normalize_repository_name(name):
    name = sanitize_text(name)
    if not name:
        return "unknown"
    match = WORKING_COPY_SUFFIX_RE.match(name)
    if match:
        return match.group("repo")
    return name


def normalize_origin(origin):
    origin = sanitize_text(origin)
    if origin.endswith(".git"):
        origin = origin[:-4]
    return origin


@lru_cache(maxsize=None)
def resolve_git_metadata(project_path):
    project_path = sanitize_text(project_path)
    if not project_path:
        return {}

    path = Path(project_path)
    candidate = path if path.is_dir() else path.parent
    if not candidate.exists():
        return {}

    try:
        rev_parse = subprocess.run(
            ["git", "-C", str(candidate), "rev-parse", "--show-toplevel", "--abbrev-ref", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return {}

    if rev_parse.returncode != 0:
        return {}

    lines = [sanitize_text(line) for line in rev_parse.stdout.splitlines() if sanitize_text(line)]
    if not lines:
        return {}

    top_level = lines[0]
    branch = lines[1] if len(lines) > 1 else ""
    if branch == "HEAD":
        branch = ""

    try:
        origin_result = subprocess.run(
            ["git", "-C", top_level, "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        origin_result = None

    origin = normalize_origin(origin_result.stdout if origin_result else "")
    return {
        "top_level": top_level,
        "branch": branch,
        "origin": origin,
    }


def build_location(repository, working_copy="", branch="", project_path="", origin="", agent=""):
    repository = sanitize_text(repository) or "unknown"
    working_copy = sanitize_text(working_copy)
    branch = sanitize_text(branch)
    project_path = sanitize_text(project_path)
    origin = normalize_origin(origin)
    agent = sanitize_text(agent)
    return {
        "repository": repository,
        "working_copy": working_copy,
        "branch": branch,
        "project_path": project_path,
        "origin": origin,
        "agent": agent,
    }


def finalize_location(location, project_path=None, agent=""):
    location = dict(location)
    if project_path:
        project_path = sanitize_text(project_path)
        if project_path:
            location["project_path"] = project_path
            git_metadata = resolve_git_metadata(project_path)
            if git_metadata.get("branch"):
                location["branch"] = git_metadata["branch"]
            if git_metadata.get("origin"):
                location["origin"] = git_metadata["origin"]
            if location.get("repository") in {"", "unknown"} and git_metadata.get("top_level"):
                top_name = Path(git_metadata["top_level"]).name
                repository = normalize_repository_name(top_name)
                location["repository"] = repository or location.get("repository") or "unknown"
                if top_name and top_name != repository and not location.get("working_copy"):
                    location["working_copy"] = top_name

    location["repository"] = sanitize_text(location.get("repository")) or "unknown"
    location["working_copy"] = sanitize_text(location.get("working_copy"))
    location["branch"] = sanitize_text(location.get("branch"))
    location["project_path"] = sanitize_text(location.get("project_path"))
    location["origin"] = normalize_origin(location.get("origin"))
    location["agent"] = sanitize_text(agent or location.get("agent"))
    if not location["origin"]:
        location["origin"] = f"local:{location['repository']}" if location["repository"] != "unknown" else "unknown"
    return location


def parse_encoded_worktree_tail(tail):
    tail = sanitize_text(tail).strip("-")
    if not tail:
        return None
    parts = [part for part in tail.split("-") if part]
    for index in range(len(parts), 0, -1):
        repository = "-".join(parts[:index])
        prefix = repository + "-"
        suffix = "-" + repository
        if tail.startswith(prefix) and tail.endswith(suffix):
            middle = tail[len(prefix) : -len(suffix)]
            if middle:
                return build_location(repository, working_copy=middle, branch=middle)
    return None


def infer_claude_location_from_rollout_path(rollout_path):
    if not rollout_path:
        return finalize_location(build_location("unknown"))

    path = Path(rollout_path)
    parts = path.parts
    try:
        project_index = parts.index("projects")
    except ValueError:
        return finalize_location(build_location(path.parent.name or path.name or "unknown", project_path=str(path)))

    if project_index + 1 >= len(parts):
        return finalize_location(build_location(path.parent.name or path.name or "unknown", project_path=str(path)))

    project_key = parts[project_index + 1]
    tail = sanitize_text(project_key).strip("-")
    worktrees_marker = "worktrees-"
    marker_index = tail.find(worktrees_marker)
    if marker_index >= 0:
        parsed = parse_encoded_worktree_tail(tail[marker_index + len(worktrees_marker) :])
        if parsed:
            parsed["project_path"] = str(path)
            return finalize_location(parsed)

    repository = normalize_repository_name(tail or project_key)
    working_copy = sanitize_text(tail or project_key)
    if working_copy == repository:
        working_copy = ""
    return finalize_location(build_location(repository, working_copy=working_copy, project_path=str(path)))


def classify_project_path(project_path):
    project_path = sanitize_text(project_path)
    if not project_path:
        return finalize_location(build_location("unknown"))

    path = Path(project_path)
    parts = path.parts
    if "worktrees" in parts:
        index = parts.index("worktrees")
        if index + 2 < len(parts):
            repository = parts[index + 1]
            working_copy = parts[index + 2]
            return finalize_location(build_location(repository, working_copy=working_copy, branch=working_copy, project_path=project_path), project_path=project_path)

    working_copy = path.name or project_path
    repository = normalize_repository_name(working_copy)
    if working_copy == repository:
        working_copy = ""
    return finalize_location(build_location(repository, working_copy=working_copy, project_path=project_path), project_path=project_path)


def resolve_location(project_path=None, claude_rollout_path=None, agent=""):
    if project_path:
        return finalize_location(classify_project_path(project_path), project_path=project_path, agent=agent)
    if claude_rollout_path:
        return finalize_location(infer_claude_location_from_rollout_path(claude_rollout_path), agent=agent)
    return finalize_location(build_location("unknown", agent=agent))


def build_source_groups(rows):
    origin_map = {}
    for row in rows:
        origin = row.get("origin") or f"local:{row.get('repository') or 'unknown'}"
        branch = row.get("branch") or ""
        repository = row.get("repository") or "unknown"
        working_copy = row.get("working_copy") or ""

        origin_group = origin_map.setdefault(
            origin,
            {
                "origin": origin,
                "totals": source_totals_template(),
                "branches": {},
            },
        )
        add_totals(origin_group["totals"], row)
        origin_group["totals"]["sessions"] += 1

        branch_group = origin_group["branches"].setdefault(
            branch,
            {
                "branch": branch,
                "totals": source_totals_template(),
                "locations": {},
            },
        )
        add_totals(branch_group["totals"], row)
        branch_group["totals"]["sessions"] += 1

        location_key = (repository, working_copy)
        location_group = branch_group["locations"].setdefault(
            location_key,
            {
                "repository": repository,
                "working_copy": working_copy,
                "branch": branch,
                "totals": source_totals_template(),
                "rows": [],
            },
        )
        add_totals(location_group["totals"], row)
        location_group["totals"]["sessions"] += 1
        location_group["rows"].append(row)

    origin_groups = []
    for origin_group in origin_map.values():
        branch_groups = []
        for branch_group in origin_group["branches"].values():
            locations = []
            for location_group in branch_group["locations"].values():
                location_group["rows"].sort(key=lambda item: item["cost_usd"], reverse=True)
                locations.append(location_group)
            locations.sort(key=lambda item: item["totals"]["cost_usd"], reverse=True)
            branch_group["locations"] = locations
            branch_groups.append(branch_group)
        branch_groups.sort(key=lambda item: item["totals"]["cost_usd"], reverse=True)
        origin_group["branches"] = branch_groups
        origin_groups.append(origin_group)

    origin_groups.sort(key=lambda item: item["totals"]["cost_usd"], reverse=True)
    return origin_groups


def format_origin_heading(origin_group):
    return f"Origin: {origin_group['origin']} ({format_value('usd', origin_group['totals']['cost_usd'])})"


def format_branch_heading(branch_group):
    branch = branch_group.get("branch") or "(no branch)"
    return f"Branch: {branch} ({format_value('usd', branch_group['totals']['cost_usd'])})"


def format_location_heading(location_group):
    details = []
    repository = location_group.get("repository") or "unknown"
    working_copy = location_group.get("working_copy") or ""
    branch = location_group.get("branch") or ""
    details.append(f"Repository: {repository}")
    if working_copy and working_copy != repository:
        label = "Worktree" if branch and working_copy == branch else "Working copy"
        details.append(f"{label}: {working_copy}")
    return " / ".join(details)


def with_optional_agent_column(columns, rows):
    if not any(sanitize_text(row.get("agent")) for row in rows):
        return columns
    insert_at = 1 if columns and columns[0][0] == "name" else 0
    return columns[:insert_at] + [("agent", "Agent", "text")] + columns[insert_at:]


def build_claude_columns(rows):
    return with_optional_agent_column(
        [
            ("name", "Dialogue", "text"),
            ("models", "Model", "text"),
            ("input_tokens", "In (MT)", "mt"),
            ("cache_read_tokens", "C_Read", "mt"),
            ("cache_write_5m_tokens", "CW_5m", "mt"),
            ("cache_write_1h_tokens", "CW_1h", "mt"),
            ("output_tokens", "Out (MT)", "mt"),
            ("cost_usd", "Cost", "usd"),
        ],
        rows,
    )


def build_codex_columns(rows):
    return with_optional_agent_column(
        [
            ("name", "Dialogue", "text"),
            ("models", "Models", "text"),
            ("input_tokens", "In (MT)", "mt"),
            ("cache_read_tokens", "Cached", "mt"),
            ("output_tokens", "Out (MT)", "mt"),
            ("reasoning_tokens", "Reason", "mt"),
            ("cost_usd", "Cost", "usd"),
        ],
        rows,
    )


def build_junie_columns(rows):
    return with_optional_agent_column(
        [
            ("name", "Task", "text"),
            ("project", "Project", "text"),
            ("models", "Models", "text"),
            ("calls", "Calls", "int"),
            ("input_tokens", "In (MT)", "mt"),
            ("cache_read_tokens", "C_Read", "mt"),
            ("cache_write_tokens", "C_Write", "mt"),
            ("output_tokens", "Out (MT)", "mt"),
            ("cost_usd", "Cost", "usd"),
        ],
        rows,
    )


def build_compact_combined_columns():
    return [
        ("name", "Dialogue", "text"),
        ("agent", "Agent", "text"),
        ("models", "Model", "text"),
        ("cost_usd", "Cost", "usd"),
    ]


def build_detailed_combined_columns():
    return [
        ("name", "Dialogue", "text"),
        ("agent", "Agent", "text"),
        ("models", "Model", "text"),
        ("calls", "Calls", "int"),
        ("input_tokens", "In (MT)", "mt"),
        ("cache_read_tokens", "Cached", "mt"),
        ("cache_write_5m_tokens", "CW_5m", "mt"),
        ("cache_write_1h_tokens", "CW_1h", "mt"),
        ("cache_write_tokens", "C_Write", "mt"),
        ("output_tokens", "Out (MT)", "mt"),
        ("reasoning_tokens", "Reason", "mt"),
        ("cost_usd", "Cost", "usd"),
    ]


def collect_claude_report(target_dates):
    entries, display_names = claude_common.collect_entries(None, target_dates=target_dates)
    session_projects = load_claude_session_projects()
    if not entries:
        return {
            "source": "claude",
            "label": "Claude",
            "columns": build_claude_columns([]),
            "groups": [],
            "rows": [],
            "totals": source_totals_template(),
        }

    session_rows = aggregate_message_max(entries)
    session_rollout_paths = {}
    for entry in entries:
        session_rollout_paths.setdefault(entry["session_id"], entry.get("path") or "")
    rows = []
    totals = source_totals_template()
    for session_id, row in session_rows.items():
        location = resolve_location(
            project_path=session_projects.get(session_id),
            claude_rollout_path=session_rollout_paths.get(session_id),
            agent="Claude",
        )
        record = {
            "name": display_names.get(session_id, session_id[:8]),
            "models": row["model"],
            "input_tokens": row["in"],
            "cache_read_tokens": row["c_read"],
            "cache_write_tokens": row["c_write_5m"] + row["c_write_1h"],
            "cache_write_5m_tokens": row["c_write_5m"],
            "cache_write_1h_tokens": row["c_write_1h"],
            "output_tokens": row["out"],
            "reasoning_tokens": 0,
            "calls": 0,
            "cost_usd": row["cost"],
            **location,
        }
        rows.append(record)
        add_totals(totals, record)
        totals["sessions"] += 1

    rows.sort(key=lambda item: item["cost_usd"], reverse=True)
    return {
        "source": "claude",
        "label": "Claude",
        "columns": build_claude_columns(rows),
        "groups": build_source_groups(rows),
        "rows": rows,
        "totals": totals,
    }


def collect_codex_report(target_dates):
    entries, display_names = codex_common.collect_entries(None, target_dates=target_dates)
    if not entries:
        return {
            "source": "codex",
            "label": "Codex",
            "columns": build_codex_columns([]),
            "groups": [],
            "rows": [],
            "totals": source_totals_template(),
        }

    session_rows = aggregate_snapshot_max(entries)
    session_project_paths = {}
    for entry in entries:
        if entry.get("project_path"):
            session_project_paths.setdefault(entry["session_id"], entry["project_path"])
    rows = []
    totals = source_totals_template()
    for session_id, session_row in session_rows.items():
        usage = session_row["usage"]
        model_names = sorted(session_row["models"].keys())
        location = resolve_location(
            project_path=session_project_paths.get(session_id),
            agent="Codex",
        )
        record = {
            "name": display_names.get(session_id, session_id),
            "models": ", ".join(model_names) if model_names else "-",
            "input_tokens": usage["in"],
            "cache_read_tokens": usage["c_read"],
            "cache_write_tokens": 0,
            "cache_write_5m_tokens": 0,
            "cache_write_1h_tokens": 0,
            "output_tokens": usage["out"],
            "reasoning_tokens": usage["reasoning"],
            "calls": 0,
            "cost_usd": session_row["cost"],
            **location,
        }
        rows.append(record)
        add_totals(totals, record)
        totals["sessions"] += 1

    rows.sort(key=lambda item: item["cost_usd"], reverse=True)
    return {
        "source": "codex",
        "label": "Codex",
        "columns": build_codex_columns(rows),
        "groups": build_source_groups(rows),
        "rows": rows,
        "totals": totals,
    }


def collect_junie_report(target_dates):
    entries, session_index = collect_junie_entries(target_date=None, target_dates=target_dates)
    if not entries:
        return {
            "source": "junie",
            "label": "Junie",
            "columns": build_junie_columns([]),
            "groups": [],
            "rows": [],
            "totals": source_totals_template(),
        }

    session_rows = aggregate_junie_entries(entries)
    rows = []
    totals = source_totals_template()
    for session_id, row in session_rows.items():
        session_info = session_index.get(session_id, {})
        location = resolve_location(project_path=session_info.get("projectDir") or "", agent="Junie")
        record = {
            "name": session_info.get("taskName") or session_id,
            "project": short_project_name(session_info.get("projectDir") or ""),
            "models": format_junie_models(row["models"]),
            "calls": row["calls"],
            "input_tokens": row["in"],
            "cache_read_tokens": row["c_read"],
            "cache_write_tokens": row["c_write"],
            "cache_write_5m_tokens": 0,
            "cache_write_1h_tokens": 0,
            "output_tokens": row["out"],
            "reasoning_tokens": 0,
            "cost_usd": row["cost"],
            **location,
        }
        rows.append(record)
        add_totals(totals, record)
        totals["sessions"] += 1

    rows.sort(key=lambda item: item["cost_usd"], reverse=True)
    return {
        "source": "junie",
        "label": "Junie",
        "columns": build_junie_columns(rows),
        "groups": build_source_groups(rows),
        "rows": rows,
        "totals": totals,
    }


def build_report(scope, anchor_date, detailed=False):
    scope_info = make_scope_info(scope, anchor_date)
    target_dates = scope_info.pop("target_dates")

    sources = [
        collect_claude_report(target_dates),
        collect_codex_report(target_dates),
        collect_junie_report(target_dates),
    ]
    sources.sort(key=lambda item: item["totals"]["cost_usd"], reverse=True)

    summary_rows = []
    grand_total = source_totals_template()
    detailed_rows = []
    for source_report in sources:
        totals = source_report["totals"]
        detailed_rows.extend(source_report["rows"])
        summary_rows.append(
            {
                "source": source_report["label"],
                "sessions": totals["sessions"],
                "calls": totals["calls"],
                "cost_usd": totals["cost_usd"],
            }
        )
        add_totals(grand_total, totals)

    summary_rows.sort(key=lambda item: item["cost_usd"], reverse=True)
    detailed_rows.sort(key=lambda item: item["cost_usd"], reverse=True)
    detail_columns = build_detailed_combined_columns() if detailed else build_compact_combined_columns()
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "scope": scope_info,
        "sources": sources,
        "groups": build_source_groups(detailed_rows),
        "detailed_columns": detail_columns,
        "rows": detailed_rows,
        "summary": summary_rows,
        "grand_total": grand_total,
    }


def format_value(kind, value):
    if kind == "usd":
        return f"${value:.6f}"
    if kind == "mt":
        return f"{value / 1_000_000:.3f}"
    if kind == "int":
        return str(value)
    return str(value or "")


TEXT_COLUMN_WIDTHS = {
    "name": 48,
    "agent": 10,
    "models": 16,
    "project": 16,
    "source": 10,
}
DEFAULT_TEXT_COLUMN_WIDTH = 24
MIN_TEXT_COLUMN_WIDTH = 4
MIN_TABLE_WIDTH = 40


def sanitize_text(value):
    value = str(value or "")
    return re.sub(r"\s+", " ", value).strip()


def truncate_text(value, max_width):
    value = sanitize_text(value)
    if max_width <= 0 or len(value) <= max_width:
        return value
    if max_width == 1:
        return "…"
    return value[: max_width - 1] + "…"


def terminal_width():
    return max(shutil.get_terminal_size((120, 20)).columns, MIN_TABLE_WIDTH)


def compute_table_widths(columns, rows, totals, indent=""):
    raw_rows = []
    for row in rows:
        raw_rows.append([format_value(kind, row.get(key)) for key, _header, kind in columns])

    raw_total = None
    if totals is not None:
        raw_total = []
        for index, (key, _header, kind) in enumerate(columns):
            if index == 0:
                raw_total.append("TOTAL")
            elif kind == "text":
                raw_total.append("")
            else:
                raw_total.append(format_value(kind, totals.get(key, 0)))

    separator_width = 3 * (len(columns) - 1)
    available_width = max(terminal_width() - len(indent), MIN_TABLE_WIDTH) - separator_width

    numeric_width = 0
    text_columns = []
    widths = [0] * len(columns)
    for index, (key, header, kind) in enumerate(columns):
        values = [header]
        values.extend(row[index] for row in raw_rows)
        if raw_total is not None:
            values.append(raw_total[index])
        column_max = max(len(value) for value in values)
        if kind == "text":
            preferred = TEXT_COLUMN_WIDTHS.get(key, DEFAULT_TEXT_COLUMN_WIDTH)
            minimum = max(len(header), min(MIN_TEXT_COLUMN_WIDTH, preferred))
            maximum = max(min(column_max, preferred), minimum)
            text_columns.append(
                {
                    "index": index,
                    "minimum": minimum,
                    "maximum": maximum,
                    "preferred": preferred,
                }
            )
        else:
            widths[index] = column_max
            numeric_width += column_max

    minimum_text_total = sum(column["minimum"] for column in text_columns)
    target_text_total = max(available_width - numeric_width, minimum_text_total)

    for column in text_columns:
        widths[column["index"]] = column["minimum"]

    remaining = max(target_text_total - minimum_text_total, 0)
    expandable = [column for column in text_columns if column["maximum"] > column["minimum"]]
    while remaining > 0 and expandable:
        progressed = False
        for column in list(expandable):
            index = column["index"]
            if widths[index] < column["maximum"]:
                widths[index] += 1
                remaining -= 1
                progressed = True
                if remaining == 0:
                    break
            if widths[index] >= column["maximum"]:
                expandable.remove(column)
        if not progressed:
            break

    prepared_rows = []
    for raw_row in raw_rows:
        prepared_rows.append(
            [truncate_text(value, widths[index]) if columns[index][2] == "text" else value for index, value in enumerate(raw_row)]
        )

    prepared_total = None
    if raw_total is not None:
        prepared_total = []
        for index, value in enumerate(raw_total):
            if columns[index][2] == "text":
                prepared_total.append(truncate_text(value, widths[index]))
            else:
                prepared_total.append(value)

    return widths, prepared_rows, prepared_total


def render_text_table(title, columns, rows, totals=None, total_label="TOTAL", indent=""):
    if title:
        print(f"{indent}{title}")

    widths, prepared_rows, prepared_total = compute_table_widths(columns, rows, totals, indent=indent)
    if prepared_total is not None and columns:
        prepared_total[0] = truncate_text(total_label, widths[0])

    def print_row(values):
        cells = []
        for index, value in enumerate(values):
            kind = columns[index][2]
            if kind == "text":
                cells.append(value.ljust(widths[index]))
            else:
                cells.append(value.rjust(widths[index]))
        print(f"{indent}{' | '.join(cells)}")

    print_row([header for _key, header, _kind in columns])
    print(f"{indent}{'-+-'.join('-' * width for width in widths)}")
    for row in prepared_rows:
        print_row(row)
    if prepared_total is not None:
        print(f"{indent}{'-+-'.join('-' * width for width in widths)}")
        print_row(prepared_total)
    print()


def render_console(report, summary_only=False):
    scope = report["scope"]
    title = (
        f"Session cost summary: {scope['mode']} "
        f"({scope['start_date']} .. {scope['end_date']})"
    )
    print(title)
    print()

    render_text_table(
        "Summary",
        [
            ("source", "Source", "text"),
            ("sessions", "Sessions", "int"),
            ("calls", "Calls", "int"),
            ("cost_usd", "Cost", "usd"),
        ],
        report["summary"],
        {
            "sessions": report["grand_total"]["sessions"],
            "calls": report["grand_total"]["calls"],
            "cost_usd": report["grand_total"]["cost_usd"],
        },
    )

    if summary_only:
        return

    groups = report.get("groups")
    detailed_columns = report.get("detailed_columns")
    if groups is None or detailed_columns is None:
        for source_report in report["sources"]:
            fallback_groups = source_report.get("groups") or []
            if not fallback_groups:
                render_text_table(source_report["label"], source_report["columns"], source_report["rows"], source_report["totals"])
                continue

            print(source_report["label"])
            print()
            for origin_group in fallback_groups:
                print(f"  {format_origin_heading(origin_group)}")
                print()
                for branch_group in origin_group["branches"]:
                    print(f"    {format_branch_heading(branch_group)}")
                    print()
                    for location_group in branch_group["locations"]:
                        title = format_location_heading(location_group)
                        render_text_table(title, source_report["columns"], location_group["rows"], location_group["totals"], indent="      ")
        return

    for origin_group in groups:
        print(format_origin_heading(origin_group))
        print()
        for branch_group in origin_group["branches"]:
            print(f"  {format_branch_heading(branch_group)}")
            print()
            for location_group in branch_group["locations"]:
                title = format_location_heading(location_group)
                render_text_table(title, detailed_columns, location_group["rows"], location_group["totals"], indent="    ")


def render_html_table(title, columns, rows, totals=None, total_label="TOTAL", indent_level=0):
    margin = indent_level * 24
    lines = [f'<h2 style="margin-left: {margin}px">{escape(title)}</h2>', f'<table style="margin-left: {margin}px">']
    lines.append("<thead><tr>" + "".join(f"<th>{escape(header)}</th>" for _key, header, _kind in columns) + "</tr></thead>")
    lines.append("<tbody>")
    for row in rows:
        line = "<tr>"
        for key, _header, kind in columns:
            value = format_value(kind, row.get(key))
            if kind == "text":
                value = sanitize_text(value)
            line += f"<td>{escape(value)}</td>"
        line += "</tr>"
        lines.append(line)

    if totals is not None:
        line = "<tr class=\"total\">"
        for index, (key, _header, kind) in enumerate(columns):
            if index == 0:
                value = total_label
            elif kind == "text":
                value = ""
            else:
                value = format_value(kind, totals.get(key, 0))
            if kind == "text":
                value = sanitize_text(value)
            line += f"<td>{escape(value)}</td>"
        line += "</tr>"
        lines.append(line)

    lines.append("</tbody></table>")
    return "\n".join(lines)


def render_html(report, summary_only=False):
    scope = report["scope"]
    parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        '<meta charset="utf-8">',
        "<title>Session cost summary</title>",
        "<style>",
        "body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; }",
        "table { border-collapse: collapse; margin-bottom: 24px; min-width: 720px; }",
        "th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; }",
        "th { background: #f3f3f3; }",
        ".total td { font-weight: 700; background: #fafafa; }",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>Session cost summary</h1>",
        f"<p>Scope: <strong>{escape(scope['mode'])}</strong> ({escape(scope['start_date'])} .. {escape(scope['end_date'])})</p>",
    ]

    parts.append(
        render_html_table(
            "Summary",
            [
                ("source", "Source", "text"),
                ("sessions", "Sessions", "int"),
                ("calls", "Calls", "int"),
                ("cost_usd", "Cost", "usd"),
            ],
            report["summary"],
            {
                "sessions": report["grand_total"]["sessions"],
                "calls": report["grand_total"]["calls"],
                "cost_usd": report["grand_total"]["cost_usd"],
            },
            indent_level=0,
        )
    )

    if not summary_only:
        groups = report.get("groups")
        detailed_columns = report.get("detailed_columns")
        if groups is not None and detailed_columns is not None:
            parts.append("<h2>Detailed sessions</h2>")
            for origin_group in groups:
                parts.append(f"<h3>{escape(format_origin_heading(origin_group))}</h3>")
                for branch_group in origin_group["branches"]:
                    parts.append(f'<h4 style="margin-left: 24px">{escape(format_branch_heading(branch_group))}</h4>')
                    for location_group in branch_group["locations"]:
                        title = format_location_heading(location_group) or "Sessions"
                        parts.append(render_html_table(title, detailed_columns, location_group["rows"], location_group["totals"], indent_level=2))
            parts.extend(["</body>", "</html>"])
            return "\n".join(parts)

        for source_report in report["sources"]:
            groups = source_report.get("groups") or []
            if not groups:
                parts.append(render_html_table(source_report["label"], source_report["columns"], source_report["rows"], source_report["totals"], indent_level=0))
                continue

            parts.append(f"<h2>{escape(source_report['label'])}</h2>")
            for origin_group in groups:
                parts.append(f'<h3 style="margin-left: 24px">{escape(format_origin_heading(origin_group))}</h3>')
                for branch_group in origin_group["branches"]:
                    parts.append(f'<h4 style="margin-left: 48px">{escape(format_branch_heading(branch_group))}</h4>')
                    for location_group in branch_group["locations"]:
                        title = format_location_heading(location_group) or "Sessions"
                        parts.append(render_html_table(title, source_report["columns"], location_group["rows"], location_group["totals"], indent_level=3))

    parts.extend(["</body>", "</html>"])
    return "\n".join(parts)


def make_json_ready(report):
    def convert(value):
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    json_report = convert(report)
    for source_report in json_report["sources"]:
        source_report.pop("columns", None)
    json_report.pop("detailed_columns", None)
    return json_report


def main():
    args = parse_args()
    anchor_date = resolve_anchor_date(args.date)
    report = build_report(args.scope, anchor_date, detailed=args.detailed)

    if args.html:
        html = render_html(report, summary_only=args.summary)
        html_path = Path(args.html)
        html_path.write_text(html, encoding="utf-8")

    if args.json:
        print(json.dumps(make_json_ready(report), ensure_ascii=False, indent=2))
    else:
        render_console(report, summary_only=args.summary)


if __name__ == "__main__":
    main()