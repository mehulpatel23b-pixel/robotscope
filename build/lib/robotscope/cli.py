"""Command-line interface for robotscope."""

from __future__ import annotations

import argparse
import sys

from .checker import run, render_json, render_text
from .crawlers import resolve_names


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="robotscope",
        description="Show what your robots.txt tells GPTBot, ClaudeBot and "
                    "every other AI crawler — verdicts, accidental-block "
                    "warnings, JSON and CI exit codes.")
    ap.add_argument("target", nargs="?", default=None,
                    help="site to audit, e.g. https://example.com")
    ap.add_argument("-f", "--file", default=None,
                    help="analyze a local robots.txt file instead of fetching")
    ap.add_argument("--bot", default=None,
                    help="restrict report to these bots (comma-separated, "
                         "names or tokens)")
    ap.add_argument("--paths", default=None,
                    help="comma-separated probe paths "
                         f"(default: {','.join(import_default())})" )
    ap.add_argument("--timeout", type=float, default=15.0,
                    help="HTTP timeout in seconds (default: 15)")
    ap.add_argument("--json", action="store_true",
                    help="emit the report as JSON")
    ap.add_argument("--fail-if-blocked", default=None, metavar="BOTS",
                    help="CI gate: exit 2 if any of these bots "
                         "(comma-separated, e.g. GPTBot,ClaudeBot) is blocked")
    return ap


def import_default():
    from .checker import DEFAULT_PROBES
    return DEFAULT_PROBES


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.target and not args.file:
        ap.error("provide a site URL or use -f/--file robots.txt")
    bot_filter = resolve_names(args.bot) if args.bot else None
    probes = ([p if p.startswith("/") else "/" + p
               for p in args.paths.split(",")] if args.paths else None)
    try:
        report = run(target=args.target, file=args.file,
                     timeout=args.timeout, probes=probes,
                     bot_filter=bot_filter)
    except RuntimeError as exc:
        print(f"robotscope: error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(render_json(report))
    else:
        print(render_text(report))

    if args.fail_if_blocked:
        gate = set(resolve_names(args.fail_if_blocked))
        hits = [b["name"] for b in report["bots"]
                if b["token"] in gate and b["verdict"] == "BLOCKED"]
        if hits:
            print(f"robotscope: CI gate failed — blocked: {', '.join(hits)}",
                  file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
