#!/usr/bin/env python3
import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from openrouter_pricing import calculate_estimated_cost, match_openrouter_model

CODEX_HISTORY_PATH = Path("~/.codex/history.jsonl").expanduser()
CODEX_SESSIONS_ROOT = Path("~/.codex/sessions").expanduser()


def parse_args(default_strategy_name):
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date in YYYY-MM-DD format. Defaults to local today.")
    parser.add_argument("--label", default=default_strategy_name, help="Strategy label shown in the output.")
    parser.add_argument(
        "--session-id",
        dest="session_ids",
        action="append",
        help="Limit calculation to the specified Codex root session id. Can be passed multiple times.",
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
    return {"in": 0, "out": 0, "c_read": 0, "reasoning": 0}


def build_session_row():
    return {
        "usage": zero_usage(),
        "cost": 0.0,
        "models": defaultdict(zero_usage),
        "reasoning": 0,
    }


def event_payload(record):
    if record.get("type") == "event_msg" and isinstance(record.get("payload"), dict):
        payload = record["payload"]
        return payload.get("type") or record.get("type"), payload

    event = record.get("event_msg") or record.get("event") or record
    payload = event.get("payload")
    if isinstance(payload, dict):
        return event.get("type") or payload.get("type"), payload
    return event.get("type"), {}


def parse_iso_ts(raw_ts):
    if not raw_ts:
        return None
    if isinstance(raw_ts, (int, float)):
        return datetime.fromtimestamp(raw_ts, tz=timezone.utc).astimezone()
    if raw_ts.endswith("Z"):
        raw_ts = raw_ts[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw_ts).astimezone()
    except ValueError:
        return None


def short_prompt(text, limit=72):
    if not text:
        return None
    text = " ".join(text.strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def iter_response_texts(payload):
    content = payload.get("content")
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("input_text") or item.get("output_text")
        if text:
            yield text


def is_noise_display_text(text):
    compact = " ".join(str(text or "").strip().split())
    if not compact:
        return True

    prefixes = (
        "# AGENTS.md instructions",
        "<environment_context>",
        "<subagent_notification>",
        "<INSTRUCTIONS>",
    )
    return compact.startswith(prefixes)


def extract_subagent_name(source):
    if isinstance(source, str):
        compact = short_prompt(source, limit=24)
        return "" if compact in {None, "cli"} else compact

    if not isinstance(source, dict):
        return ""

    subagent = source.get("subagent")
    if isinstance(subagent, str):
        compact = short_prompt(subagent, limit=24)
        return compact or ""

    if isinstance(subagent, dict):
        for key in ("name", "role", "type"):
            compact = short_prompt(subagent.get(key), limit=24)
            if compact:
                return compact

    return ""


def get_display_names():
    names = {}
    if not CODEX_HISTORY_PATH.exists():
        return names

    with CODEX_HISTORY_PATH.open() as f:
        for line in f:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            sid = data.get("session_id") or data.get("sessionId") or data.get("id")
            if not sid:
                continue

            display = (
                short_prompt(data.get("title"))
                or short_prompt(data.get("text"))
                or short_prompt(data.get("prompt"))
                or short_prompt(data.get("display"))
            )
            if display:
                names.setdefault(sid, display)

    return names


def get_model_label(model_name, snapshot=None):
    entry = match_openrouter_model(model_name, snapshot=snapshot)
    if not entry:
        return model_name or "unknown"
    return entry.get("display_name") or entry.get("canonical_slug") or entry["id"]


def token_usage_from_payload(payload):
    info = payload.get("info") or payload
    total = info.get("total_token_usage") or info.get("total_usage") or info.get("usage") or {}
    if not isinstance(total, dict) or not total:
        return None

    input_tokens = int(total.get("input_tokens") or 0)
    cached_input_tokens = int(total.get("cached_input_tokens") or 0)
    output_tokens = int(total.get("output_tokens") or 0)
    reasoning_tokens = int(total.get("reasoning_output_tokens") or 0)

    return {
        "in": max(input_tokens - cached_input_tokens, 0),
        "out": output_tokens,
        "c_read": cached_input_tokens,
        "reasoning": reasoning_tokens,
    }


def iter_rollout_paths(target_date=None, target_dates=None):
    active_dates = set(target_dates or [])
    if target_date is not None:
        active_dates.add(target_date)

    local_dates = set()
    for day in active_dates:
        local_dates.add(day - timedelta(days=1))
        local_dates.add(day)
        local_dates.add(day + timedelta(days=1))

    seen = set()
    for day in sorted(local_dates):
        day_dir = CODEX_SESSIONS_ROOT / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}"
        if not day_dir.exists():
            continue
        for path in sorted(day_dir.glob("rollout-*.jsonl")):
            if path not in seen:
                seen.add(path)
                yield path


def session_file_fallback_name(path):
    stem = path.stem
    if stem.startswith("rollout-"):
        suffix = stem[len("rollout-") :]
        if len(suffix) > 36:
            maybe_sid = suffix[-36:]
            if maybe_sid.count("-") == 4:
                return maybe_sid
    return stem


def extract_session_meta(path):
    session_id = None
    parent_session_id = None
    model = None
    display = None
    fallback_display = None
    agent = ""
    cwd_path = None
    cwd_name = None
    saw_session_meta = False

    try:
        with path.open() as f:
            for line in f:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type, payload = event_payload(record)
                if event_type == "session_meta":
                    saw_session_meta = True
                    session_id = payload.get("id") or payload.get("session_id") or payload.get("sessionId") or session_id
                    model = payload.get("model") or payload.get("model_name") or model
                    cwd = payload.get("cwd") or payload.get("workdir") or payload.get("workspace")
                    if cwd:
                        cwd_path = cwd
                        cwd_name = Path(cwd).name or cwd_name
                    display = short_prompt(payload.get("title") or payload.get("text") or payload.get("prompt")) or display
                    source = payload.get("source") or {}
                    agent = extract_subagent_name(source) or agent
                    if isinstance(source, dict):
                        subagent = source.get("subagent") or {}
                        if isinstance(subagent, dict):
                            thread_spawn = subagent.get("thread_spawn") or {}
                            if isinstance(thread_spawn, dict):
                                parent_session_id = thread_spawn.get("parent_thread_id") or parent_session_id
                    if model and session_id and (display or fallback_display):
                        break
                    continue

                if event_type == "turn_context":
                    model = payload.get("model") or model
                    cwd = payload.get("cwd")
                    if cwd:
                        cwd_path = cwd
                        cwd_name = Path(cwd).name or cwd_name
                    if saw_session_meta and model and session_id and (display or fallback_display):
                        break

                if event_type == "response_item" and payload.get("role") == "user" and not display:
                    for text in iter_response_texts(payload):
                        if is_noise_display_text(text):
                            continue
                        display = short_prompt(text)
                        if display:
                            break

                if event_type == "response_item" and payload.get("role") == "assistant" and not fallback_display:
                    for text in iter_response_texts(payload):
                        if is_noise_display_text(text):
                            continue
                        fallback_display = short_prompt(text)
                        if fallback_display:
                            break

                if event_type == "agent_message" and not fallback_display:
                    message = payload.get("message")
                    if not is_noise_display_text(message):
                        fallback_display = short_prompt(message)
    except OSError:
        pass

    if not display:
        display = fallback_display

    return {
        "session_id": session_id or session_file_fallback_name(path),
        "parent_session_id": parent_session_id,
        "model": model,
        "display": display,
        "agent": agent,
        "cwd_path": cwd_path,
        "cwd_name": cwd_name,
        "path": path,
    }


def build_session_graph(target_date=None, target_dates=None):
    meta_by_session = {}
    for path in iter_rollout_paths(target_date=target_date, target_dates=target_dates):
        meta = extract_session_meta(path)
        meta_by_session[meta["session_id"]] = meta
    return meta_by_session


def resolve_root_session_id(session_id, meta_by_session):
    current = session_id
    seen = set()
    while current and current not in seen:
        seen.add(current)
        meta = meta_by_session.get(current)
        if not meta or not meta.get("parent_session_id"):
            return current
        current = meta["parent_session_id"]
    return session_id


def collect_entries(target_date, allowed_root_session_ids=None, target_dates=None):
    allowed_root_session_ids = set(allowed_root_session_ids or [])
    meta_by_session = build_session_graph(target_date=target_date, target_dates=target_dates)
    display_names = get_display_names()
    entries = []

    for meta in meta_by_session.values():
        path = meta["path"]
        session_id = meta["session_id"]
        root_session_id = resolve_root_session_id(session_id, meta_by_session)
        if allowed_root_session_ids and root_session_id not in allowed_root_session_ids:
            continue

        with path.open() as f:
            for line in f:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                local_dt = parse_iso_ts(record.get("timestamp") or record.get("ts"))
                if not local_dt:
                    continue

                local_date = local_dt.date()
                if target_dates is not None:
                    if local_date not in target_dates:
                        continue
                elif local_date != target_date:
                    continue

                event_type, payload = event_payload(record)
                if event_type != "token_count":
                    continue

                usage = token_usage_from_payload(payload)
                if not usage:
                    continue

                snapshot_id = (
                    payload.get("turn_id")
                    or payload.get("message_id")
                    or payload.get("id")
                    or record.get("id")
                    or f"{session_id}:{record.get('timestamp') or record.get('ts') or len(entries)}"
                )
                model_name = payload.get("model") or payload.get("model_name") or meta.get("model")
                preferred_display = meta.get("display")
                fallback_display = display_names.get(root_session_id) or display_names.get(session_id) or meta.get("cwd_name") or root_session_id
                if preferred_display:
                    display_names[root_session_id] = preferred_display
                else:
                    display_names.setdefault(root_session_id, fallback_display)

                entries.append(
                    {
                        "session_id": root_session_id,
                        "leaf_session_id": session_id,
                        "snapshot_id": snapshot_id,
                        "timestamp": local_dt,
                        "usage": usage,
                        "model": model_name,
                        "agent": meta.get("agent") or "",
                        "project_path": meta.get("cwd_path") or "",
                    }
                )

    return entries, display_names


def add_session_usage(session_row, usage, model_name, snapshot=None):
    session_row["usage"]["in"] += usage["in"]
    session_row["usage"]["out"] += usage["out"]
    session_row["usage"]["c_read"] += usage["c_read"]
    session_row["usage"]["reasoning"] += usage["reasoning"]

    _entry, cost = calculate_estimated_cost(
        model_name,
        input_tokens=usage["in"],
        output_tokens=usage["out"],
        cache_read_tokens=usage["c_read"],
        snapshot=snapshot,
    )

    session_row["cost"] += cost or 0.0

    model_usage = session_row["models"][get_model_label(model_name, snapshot=snapshot)]
    model_usage["in"] += usage["in"]
    model_usage["out"] += usage["out"]
    model_usage["c_read"] += usage["c_read"]
    model_usage["reasoning"] += usage["reasoning"]


def group_entries_by_snapshot(entries):
    grouped = defaultdict(list)
    for entry in entries:
        grouped[(entry["leaf_session_id"], entry["snapshot_id"])] .append(entry)
    return grouped


def format_models(model_usage_map):
    if not model_usage_map:
        return "-"
    parts = []
    for model_key, usage in sorted(
        model_usage_map.items(),
        key=lambda item: item[1]["in"] + item[1]["c_read"] + item[1]["out"],
        reverse=True,
    ):
        parts.append(model_key)
    return ", ".join(parts)


def print_summary(label, target_date, session_rows, display_names):
    rows = []
    total_cost = 0.0
    total_in = 0
    total_cached = 0
    total_out = 0
    total_reasoning = 0

    for sid, session_row in session_rows.items():
        usage = session_row["usage"]
        cost = session_row["cost"]
        rows.append(
            {
                "dialogue": display_names.get(sid, sid),
                "models": format_models(session_row["models"]),
                "in_m": usage["in"] / 1_000_000,
                "cached_m": usage["c_read"] / 1_000_000,
                "out_m": usage["out"] / 1_000_000,
                "reasoning_m": usage["reasoning"] / 1_000_000,
                "cost": cost,
            }
        )
        total_cost += cost
        total_in += usage["in"]
        total_cached += usage["c_read"]
        total_out += usage["out"]
        total_reasoning += usage["reasoning"]

    rows.sort(key=lambda row: row["cost"], reverse=True)

    dialogue_width = max([len(row["dialogue"]) for row in rows] + [8])
    model_width = max([len(row["models"]) for row in rows] + [6])

    print(f"Codex cost summary ({label}) for {target_date}")
    print(
        f"{'Dialogue':<{dialogue_width}}  {'Models':<{model_width}}  {'In(M)':>10}  {'Cached(M)':>10}  {'Out(M)':>10}  {'Reason(M)':>10}  {'Cost($)':>10}"
    )
    print("-" * (dialogue_width + model_width + 68))

    for row in rows:
        print(
            f"{row['dialogue']:<{dialogue_width}}  "
            f"{row['models']:<{model_width}}  "
            f"{row['in_m']:>10.3f}  "
            f"{row['cached_m']:>10.3f}  "
            f"{row['out_m']:>10.3f}  "
            f"{row['reasoning_m']:>10.3f}  "
            f"{row['cost']:>10.4f}"
        )

    print("-" * (dialogue_width + model_width + 68))
    print(
        f"{'TOTAL':<{dialogue_width}}  {'-':<{model_width}}  "
        f"{total_in / 1_000_000:>10.3f}  "
        f"{total_cached / 1_000_000:>10.3f}  "
        f"{total_out / 1_000_000:>10.3f}  "
        f"{total_reasoning / 1_000_000:>10.3f}  "
        f"{total_cost:>10.4f}"
    )
