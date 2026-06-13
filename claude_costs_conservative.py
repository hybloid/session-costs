#!/usr/bin/env python3
from collections import defaultdict

from claude_costs_common import (
    add_session_usage,
    build_session_row,
    collect_entries,
    group_entries_by_message,
    parse_args,
    print_summary,
    resolve_target_date,
    zero_usage,
)
from pricing_catalog import get_pricing_catalog


def aggregate_message_max(entries):
    session_rows = defaultdict(build_session_row)
    snapshot = get_pricing_catalog()

    for (sid, _mid), message_entries in group_entries_by_message(entries).items():
        message_usage = zero_usage()
        last_model = None

        for entry in message_entries:
            usage = entry["usage"]
            message_usage["in"] = max(message_usage["in"], usage["in"])
            message_usage["out"] = max(message_usage["out"], usage["out"])
            message_usage["c_read"] = max(message_usage["c_read"], usage["c_read"])
            message_usage["c_write_5m"] = max(message_usage["c_write_5m"], usage["c_write_5m"])
            message_usage["c_write_1h"] = max(message_usage["c_write_1h"], usage["c_write_1h"])
            if entry["model"]:
                last_model = entry["model"]

        add_session_usage(session_rows[sid], message_usage, last_model, snapshot=snapshot)

    return session_rows


def main():
    args = parse_args("conservative-message-max")
    target_date = resolve_target_date(args.date)
    entries, sid_display_names = collect_entries(target_date, args.session_ids)

    if not entries:
        print(f"No Claude usage found for {target_date}.")
        return

    session_rows = aggregate_message_max(entries)
    print_summary(args.label, target_date, session_rows, sid_display_names)


if __name__ == "__main__":
    main()