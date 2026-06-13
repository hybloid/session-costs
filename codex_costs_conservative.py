#!/usr/bin/env python3
from collections import defaultdict

from codex_costs_common import (
    add_session_usage,
    build_session_row,
    collect_entries,
    get_model_key,
    group_entries_by_snapshot,
    parse_args,
    print_summary,
    resolve_target_date,
    zero_usage,
)


def aggregate_snapshot_max(entries):
    session_rows = defaultdict(build_session_row)

    leaf_totals = {}
    for entry in entries:
        leaf_session_id = entry["leaf_session_id"]
        session_id = entry["session_id"]
        usage = entry["usage"]
        current = leaf_totals.setdefault(
            leaf_session_id,
            {
                "session_id": session_id,
                "usage": zero_usage(),
                "model": None,
            },
        )
        current["usage"]["in"] = max(current["usage"]["in"], usage["in"])
        current["usage"]["out"] = max(current["usage"]["out"], usage["out"])
        current["usage"]["c_read"] = max(current["usage"]["c_read"], usage["c_read"])
        current["usage"]["reasoning"] = max(current["usage"]["reasoning"], usage["reasoning"])
        if entry["model"]:
            current["model"] = entry["model"]

    for leaf_total in leaf_totals.values():
        add_session_usage(
            session_rows[leaf_total["session_id"]],
            leaf_total["usage"],
            get_model_key(leaf_total["model"]),
        )

    return session_rows


def main():
    args = parse_args("conservative-snapshot-max")
    target_date = resolve_target_date(args.date)
    entries, sid_display_names = collect_entries(target_date, args.session_ids)

    if not entries:
        print(f"No Codex usage found for {target_date}.")
        return

    session_rows = aggregate_snapshot_max(entries)
    print_summary(args.label, target_date, session_rows, sid_display_names)


if __name__ == "__main__":
    main()
