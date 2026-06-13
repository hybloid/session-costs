#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from datetime import date, datetime
from pathlib import Path

JUNIE_HOME = Path("~/.junie").expanduser()
JUNIE_SESSIONS_ROOT = JUNIE_HOME / "sessions"
JUNIE_INDEX_PATH = JUNIE_SESSIONS_ROOT / "index.jsonl"
JUNIE_COST_QUANTUM = Decimal("0.0000000001")


def parse_args():
    parser = argparse.ArgumentParser()
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--date", help="Date in YYYY-MM-DD format. Defaults to local today.")
    scope.add_argument("--all-time", action="store_true", help="Sum the full session history without date filtering.")
    parser.add_argument("--label", default="direct-event-cost", help="Label shown in the output header.")
    parser.add_argument(
        "--session-id",
        dest="session_ids",
        action="append",
        help="Limit calculation to the specified Junie session id. Can be passed multiple times.",
    )
    return parser.parse_args()


def resolve_target_date(raw_date, all_time):
    if all_time:
        return None
    if not raw_date:
        return date.today()
    try:
        return date.fromisoformat(raw_date)
    except ValueError:
        print(f"Invalid --date value: {raw_date}", file=sys.stderr)
        sys.exit(2)


def load_session_index(index_path=JUNIE_INDEX_PATH):
    index = {}
    if not index_path.exists():
        return index

    with index_path.open() as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            session_id = record.get("sessionId")
            if session_id:
                index[session_id] = record

    return index


def iter_session_dirs(sessions_root=JUNIE_SESSIONS_ROOT):
    if not sessions_root.exists():
        print(f"Error: {sessions_root} does not exist.", file=sys.stderr)
        sys.exit(1)

    for path in sorted(sessions_root.iterdir()):
        if path.is_dir() and path.name.startswith("session-"):
            yield path


def normalize_model_usage(model_usage):
    if isinstance(model_usage, dict):
        return [model_usage]
    if isinstance(model_usage, list):
        return [item for item in model_usage if isinstance(item, dict)]
    return []


def normalize_cost_value(raw_cost):
    if raw_cost is None:
        return Decimal("0")
    value = raw_cost if isinstance(raw_cost, Decimal) else Decimal(str(raw_cost))
    return value.quantize(JUNIE_COST_QUANTUM).normalize()


def event_local_date(timestamp_ms):
    if timestamp_ms is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000).date()
    except (TypeError, ValueError, OSError):
        return None


def matches_target_date(local_date, target_date=None, target_dates=None):
    if target_dates is not None:
        return local_date in target_dates
    return local_date == target_date


def target_date_bounds(target_date=None, target_dates=None):
    if target_dates:
        ordered = sorted(target_dates)
        return ordered[0], ordered[-1]
    if target_date is not None:
        return target_date, target_date
    return None, None


def session_may_match_target_dates(session_info, target_date=None, target_dates=None):
    start_date, end_date = target_date_bounds(target_date, target_dates)
    if start_date is None or end_date is None:
        return True

    created_date = event_local_date(session_info.get("createdAt"))
    updated_date = event_local_date(session_info.get("updatedAt"))
    if created_date and created_date > end_date:
        return False
    if updated_date and updated_date < start_date:
        return False
    return True


def collect_entries(target_date=None, session_ids=None, sessions_root=JUNIE_SESSIONS_ROOT, index_path=JUNIE_INDEX_PATH, target_dates=None):
    session_filter = set(session_ids or [])
    session_index = load_session_index(index_path)
    entries = []

    for session_dir in iter_session_dirs(sessions_root):
        session_id = session_dir.name
        if session_filter and session_id not in session_filter:
            continue

        session_info = session_index.get(session_id, {})
        if not session_may_match_target_dates(session_info, target_date=target_date, target_dates=target_dates):
            continue

        events_path = session_dir / "events.jsonl"
        if not events_path.exists():
            continue

        with events_path.open() as f:
            for line in f:
                try:
                    record = json.loads(line, parse_float=Decimal)
                except json.JSONDecodeError:
                    continue

                local_date = event_local_date(record.get("timestampMs"))
                if local_date is None:
                    continue

                if target_date is not None or target_dates is not None:
                    if not matches_target_date(local_date, target_date, target_dates):
                        continue

                agent_event = ((record.get("event") or {}).get("agentEvent") or {})
                model_usage = normalize_model_usage(agent_event.get("modelUsage"))
                if not model_usage:
                    continue

                for usage in model_usage:
                    entries.append(
                        {
                            "session_id": session_id,
                            "task_name": session_info.get("taskName") or session_id,
                            "project_dir": session_info.get("projectDir") or "",
                            "model": usage.get("model") or "unknown",
                            "cost": normalize_cost_value(usage.get("cost") or 0),
                            "in": int(usage.get("inputTokens") or 0),
                            "c_read": int(usage.get("cacheInputTokens") or 0),
                            "c_write": int(usage.get("cacheCreateTokens") or 0),
                            "out": int(usage.get("outputTokens") or 0),
                        }
                    )

    return entries, session_index


def build_session_row():
    return {"cost": Decimal("0"), "calls": 0, "in": 0, "c_read": 0, "c_write": 0, "out": 0, "models": Counter()}


def aggregate_entries(entries):
    session_rows = defaultdict(build_session_row)

    for entry in entries:
        row = session_rows[entry["session_id"]]
        row["cost"] += entry["cost"]
        row["calls"] += 1
        row["in"] += entry["in"]
        row["c_read"] += entry["c_read"]
        row["c_write"] += entry["c_write"]
        row["out"] += entry["out"]
        row["models"][entry["model"]] += entry["cost"]

    return session_rows


def short_project_name(project_dir):
    if not project_dir:
        return "-"
    return Path(project_dir).name or project_dir


def format_models(counter):
    if not counter:
        return "-"
    ordered = counter.most_common()
    head = ordered[0][0]
    if len(ordered) == 1:
        return head
    return f"{head} +{len(ordered) - 1}"


def print_summary(label, target_date, session_rows, session_index):
    scope_label = target_date.isoformat() if target_date else "all time"
    print(f"\nJunie Cost Summary for {scope_label} ({label})")
    print("=" * 153)
    print(
        f"{'Task Name':<45} | {'Project':<18} | {'Models':<20} | {'Calls':>5} | {'In (MT)':<8} | {'C_Read':<8} | {'C_Write':<8} | {'Out (MT)':<8} | {'Cost'}"
    )
    print("-" * 153)

    grand = build_session_row()
    ordered_rows = []
    for session_id, row in session_rows.items():
        session_info = session_index.get(session_id, {})
        ordered_rows.append(
            (
                session_info.get("taskName") or session_id,
                short_project_name(session_info.get("projectDir") or ""),
                format_models(row["models"]),
                row,
            )
        )
        grand["cost"] += row["cost"]
        grand["calls"] += row["calls"]
        grand["in"] += row["in"]
        grand["c_read"] += row["c_read"]
        grand["c_write"] += row["c_write"]
        grand["out"] += row["out"]

    ordered_rows.sort(key=lambda item: item[3]["cost"], reverse=True)

    for task_name, project_name, models, row in ordered_rows:
        if len(task_name) > 43:
            task_name = task_name[:40] + "..."
        if len(project_name) > 18:
            project_name = project_name[:15] + "..."
        if len(models) > 20:
            models = models[:17] + "..."
        print(
            f"{task_name:<45} | {project_name:<18} | {models:<20} | {row['calls']:>5} | {row['in'] / 1e6:>8.2f} | {row['c_read'] / 1e6:>8.2f} | {row['c_write'] / 1e6:>8.2f} | {row['out'] / 1e6:>8.2f} | ${row['cost']:>10.6f}"
        )

    print("-" * 153)
    print(
        f"{'TOTAL':<45} | {'':<18} | {'':<20} | {grand['calls']:>5} | {grand['in'] / 1e6:>8.2f} | {grand['c_read'] / 1e6:>8.2f} | {grand['c_write'] / 1e6:>8.2f} | {grand['out'] / 1e6:>8.2f} | ${grand['cost']:>10.6f}"
    )
    print("=" * 153 + "\n")


def main():
    args = parse_args()
    target_date = resolve_target_date(args.date, args.all_time)
    entries, session_index = collect_entries(target_date=target_date, session_ids=args.session_ids)

    if not entries:
        scope_label = target_date.isoformat() if target_date else "all time"
        print(f"No Junie usage found for {scope_label}.")
        return

    session_rows = aggregate_entries(entries)
    print_summary(args.label, target_date, session_rows, session_index)


if __name__ == "__main__":
    main()