#!/usr/bin/env python3
import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from openrouter_pricing import calculate_estimated_cost, match_openrouter_model


def parse_args(default_strategy_name):
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date in YYYY-MM-DD format. Defaults to local today.")
    parser.add_argument("--label", default=default_strategy_name, help="Strategy label shown in the output.")
    parser.add_argument(
        "--session-id",
        dest="session_ids",
        action="append",
        help="Limit calculation to the specified Claude session id. Can be passed multiple times.",
    )
    return parser.parse_args()


def resolve_target_date(raw_date):
    if not raw_date:
        return date.today()
    try:
        return date.fromisoformat(raw_date)
    except ValueError:
        print(f"Invalid --date value: {raw_date}", file=sys.stderr)
        sys.exit(2)


def zero_usage():
    return {"in": 0, "out": 0, "c_read": 0, "c_write_5m": 0, "c_write_1h": 0}


def get_model_label(model_name, snapshot=None):
    entry = match_openrouter_model(model_name, snapshot=snapshot)
    if not entry:
        return model_name or "unknown"
    return entry.get("display_name") or entry.get("canonical_slug") or entry["id"]


def get_display_names():
    history_path = Path("~/.claude/history.jsonl").expanduser()
    names = {}
    if not history_path.exists():
        return names

    with open(history_path, "r") as f:
        for line in f:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            sid = data.get("sessionId")
            display = data.get("display")
            if not sid or not display:
                continue

            is_slash = display.startswith("/")
            if sid not in names or (names[sid].startswith("/") and not is_slash):
                names[sid] = display

    return names


def parse_usage(usage_dict):
    cache_creation = usage_dict.get("cache_creation", {})
    write_5m = cache_creation.get("ephemeral_5m_input_tokens")
    write_1h = cache_creation.get("ephemeral_1h_input_tokens")
    total_write = usage_dict.get("cache_creation_input_tokens", 0)

    if write_5m is None and write_1h is None:
        write_5m = total_write
        write_1h = 0
    else:
        write_5m = write_5m or 0
        write_1h = write_1h or 0

    return {
        "in": usage_dict.get("input_tokens", 0),
        "out": usage_dict.get("output_tokens", 0),
        "c_read": usage_dict.get("cache_read_input_tokens", 0),
        "c_write_5m": write_5m,
        "c_write_1h": write_1h,
    }


def utc_to_local(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(tz=None)
    except ValueError:
        return None


def matches_target_date(local_date, target_date=None, target_dates=None):
    if target_dates is not None:
        return local_date in target_dates
    return local_date == target_date


def infer_display_name(jsonl_file, sid, history_display_names):
    name = history_display_names.get(sid)
    if name:
        return name

    for part in str(jsonl_file).split("/"):
        if part.startswith("-Users-"):
            return part.split("-")[-1]

    return sid[:8]


def collect_entries(target_date, session_ids=None, target_dates=None):
    projects_dir = Path("~/.claude/projects/").expanduser()
    history_display_names = get_display_names()
    sid_display_names = {}
    entries = []
    session_filter = set(session_ids or [])

    if not projects_dir.exists():
        print(f"Error: {projects_dir} does not exist.", file=sys.stderr)
        sys.exit(1)

    for jsonl_file in projects_dir.rglob("*.jsonl"):
        try:
            with open(jsonl_file, "r") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if data.get("type") != "assistant":
                        continue

                    ts_str = data.get("timestamp")
                    if not ts_str:
                        continue

                    local_dt = utc_to_local(ts_str)
                    if not local_dt or not matches_target_date(local_dt.date(), target_date, target_dates):
                        continue

                    sid = data.get("sessionId")
                    msg = data.get("message", {})
                    mid = msg.get("id")
                    usage = msg.get("usage")
                    if not sid or not mid or not usage:
                        continue

                    if session_filter and sid not in session_filter:
                        continue

                    if sid not in sid_display_names:
                        sid_display_names[sid] = infer_display_name(jsonl_file, sid, history_display_names)

                    entries.append({
                        "session_id": sid,
                        "message_id": mid,
                        "request_id": data.get("requestId"),
                        "stop_reason": msg.get("stop_reason"),
                        "model": msg.get("model") or data.get("model"),
                        "usage": parse_usage(usage),
                        "timestamp": ts_str,
                        "path": str(jsonl_file),
                    })
        except OSError:
            continue

    return entries, sid_display_names


def calculate_cost(usage, model_name, snapshot=None):
    _entry, cost = calculate_estimated_cost(
        model_name,
        input_tokens=usage["in"],
        output_tokens=usage["out"],
        cache_read_tokens=usage["c_read"],
        cache_write_5m_tokens=usage["c_write_5m"],
        cache_write_1h_tokens=usage["c_write_1h"],
        snapshot=snapshot,
    )
    return cost or 0.0


def build_session_row():
    return {"in": 0, "out": 0, "c_read": 0, "c_write_5m": 0, "c_write_1h": 0, "cost": 0.0, "model": "unknown"}


def add_session_usage(row, usage, model_name, snapshot=None):
    row["in"] += usage["in"]
    row["out"] += usage["out"]
    row["c_read"] += usage["c_read"]
    row["c_write_5m"] += usage["c_write_5m"]
    row["c_write_1h"] += usage["c_write_1h"]
    row["cost"] += calculate_cost(usage, model_name, snapshot=snapshot)
    row["model"] = get_model_label(model_name, snapshot=snapshot)


def print_summary(strategy_name, target_date, session_rows, sid_display_names):
    print(f"\nClaude Cost Summary for {target_date} ({strategy_name})")
    print("=" * 145)
    print(
        f"{'Dialogue Name':<45} | {'Model':<12} | {'In (MT)':<8} | {'Out (MT)':<8} | {'C_Read':<8} | {'CW_5m':<8} | {'CW_1h':<8} | {'Cost'}"
    )
    print("-" * 145)

    grand = build_session_row()
    ordered_rows = []
    for sid, row in session_rows.items():
        ordered_rows.append((sid_display_names.get(sid, sid[:8]), row))
        grand["in"] += row["in"]
        grand["out"] += row["out"]
        grand["c_read"] += row["c_read"]
        grand["c_write_5m"] += row["c_write_5m"]
        grand["c_write_1h"] += row["c_write_1h"]
        grand["cost"] += row["cost"]

    ordered_rows.sort(key=lambda item: item[1]["cost"], reverse=True)

    for name, row in ordered_rows:
        if len(name) > 43:
            name = name[:40] + "..."
        print(
            f"{name:<45} | {row['model']:<12} | {row['in'] / 1e6:>8.2f} | {row['out'] / 1e6:>8.2f} | {row['c_read'] / 1e6:>8.2f} | {row['c_write_5m'] / 1e6:>8.2f} | {row['c_write_1h'] / 1e6:>8.2f} | ${row['cost']:>8.2f}"
        )

    print("-" * 145)
    print(
        f"{'TOTAL':<45} | {'':<12} | {grand['in'] / 1e6:>8.2f} | {grand['out'] / 1e6:>8.2f} | {grand['c_read'] / 1e6:>8.2f} | {grand['c_write_5m'] / 1e6:>8.2f} | {grand['c_write_1h'] / 1e6:>8.2f} | ${grand['cost']:>8.2f}"
    )
    print("=" * 145 + "\n")


def group_entries_by_message(entries):
    grouped = defaultdict(list)
    for entry in entries:
        grouped[(entry["session_id"], entry["message_id"])].append(entry)
    return grouped