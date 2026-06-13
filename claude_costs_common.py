#!/usr/bin/env python3
import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

PRICING = {
    "sonnet": {"in": 3.0, "out": 15.0, "c_write_5m": 3.75, "c_write_1h": 6.0, "c_read": 0.30},
    "opus": {"in": 5.0, "out": 25.0, "c_write_5m": 6.25, "c_write_1h": 10.0, "c_read": 0.50},
    "opus_legacy": {"in": 15.0, "out": 75.0, "c_write_5m": 18.75, "c_write_1h": 30.0, "c_read": 1.50},
    "haiku": {"in": 1.0, "out": 5.0, "c_write_5m": 1.25, "c_write_1h": 2.0, "c_read": 0.10},
    "haiku_legacy": {"in": 0.8, "out": 4.0, "c_write_5m": 1.0, "c_write_1h": 1.6, "c_read": 0.08},
    "fable": {"in": 10.0, "out": 50.0, "c_write_5m": 12.5, "c_write_1h": 20.0, "c_read": 1.0},
    "mythos": {"in": 10.0, "out": 50.0, "c_write_5m": 12.5, "c_write_1h": 20.0, "c_read": 1.0},
}

MODEL_MAPPING = [
    ("claude-mythos-5", "mythos"),
    ("claude-fable-5", "fable"),
    ("claude-opus-4-8", "opus"),
    ("claude-opus-4-7", "opus"),
    ("claude-opus-4-6", "opus"),
    ("claude-opus-4-5", "opus"),
    ("claude-opus-4-1", "opus_legacy"),
    ("claude-opus-4", "opus_legacy"),
    ("claude-sonnet-4-6", "sonnet"),
    ("claude-sonnet-4-5", "sonnet"),
    ("claude-sonnet-4", "sonnet"),
    ("claude-3-5-sonnet", "sonnet"),
    ("claude-haiku-4-5", "haiku"),
    ("claude-3-5-haiku", "haiku_legacy"),
    ("mythos", "mythos"),
    ("fable", "fable"),
    ("opus", "opus"),
    ("sonnet", "sonnet"),
    ("haiku", "haiku"),
]


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


def get_model_key(model_name):
    if not model_name:
        return "sonnet"
    lowered = model_name.lower()
    for needle, model_key in MODEL_MAPPING:
        if needle in lowered:
            return model_key
    return "sonnet"


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


def calculate_cost(usage, model_key):
    rates = PRICING[model_key]
    return (
        usage["in"] * rates["in"]
        + usage["out"] * rates["out"]
        + usage["c_read"] * rates["c_read"]
        + usage["c_write_5m"] * rates["c_write_5m"]
        + usage["c_write_1h"] * rates["c_write_1h"]
    ) / 1_000_000


def build_session_row():
    return {"in": 0, "out": 0, "c_read": 0, "c_write_5m": 0, "c_write_1h": 0, "cost": 0.0, "model": "sonnet"}


def add_session_usage(row, usage, model_key):
    row["in"] += usage["in"]
    row["out"] += usage["out"]
    row["c_read"] += usage["c_read"]
    row["c_write_5m"] += usage["c_write_5m"]
    row["c_write_1h"] += usage["c_write_1h"]
    row["cost"] += calculate_cost(usage, model_key)
    row["model"] = model_key


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