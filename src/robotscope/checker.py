"""Fetch a robots.txt, evaluate it for every known AI crawler, build a report."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

from .crawlers import CRAWLERS
from .parser import RobotsDoc, is_allowed, parse

DEFAULT_PROBES = ["/", "/blog/", "/pricing", "/docs/", "/news/latest", "/p/123"]

USER_AGENT = "robotscope/1.0 (+https://github.com/mehulpatel23b-pixel/robotscope)"


def normalize_target(target: str) -> str:
    """Normalize user input into a scheme://host URL."""
    target = target.strip()
    if "://" not in target:
        target = "https://" + target
    return target.rstrip("/")


def robots_url(target: str) -> str:
    from urllib.parse import urlsplit
    parts = urlsplit(normalize_target(target))
    return f"{parts.scheme}://{parts.netloc}/robots.txt"


def fetch(url: str, timeout: float = 15.0) -> Tuple[int, str]:
    """Fetch a URL -> (status, body). HTTP errors return their status."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "text/plain,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return -1, ""


def evaluate_bot(doc: RobotsDoc, crawler: Dict[str, str],
                 probes: List[str]) -> Dict:
    """Produce the verdict row for one crawler against the parsed robots.txt."""
    blocked, allowed = [], []
    source = "none"
    for path in probes:
        ok, src = is_allowed(doc, crawler["token"], path)
        source = src
        (allowed if ok else blocked).append(path)
    _, delay, rule_source = doc.rules_for(crawler["token"])
    verdict = "ALLOWED"
    if blocked and not allowed:
        verdict = "BLOCKED"
    elif blocked and allowed:
        verdict = "PARTIAL"
    elif rule_source == "none":
        verdict = "DEFAULT"  # no robots.txt rules apply at all
    return {
        "token": crawler["token"],
        "name": crawler["name"],
        "company": crawler["company"],
        "kind": crawler["kind"],
        "note": crawler["note"],
        "verdict": verdict,
        "rules_from": rule_source if verdict != "DEFAULT" else "none",
        "crawl_delay": delay,
        "blocked_paths": blocked,
        "allowed_paths": allowed,
    }


def build_warnings(doc: RobotsDoc, missing: bool, bots: List[Dict]) -> List[str]:
    warnings: List[str] = []
    if missing:
        warnings.append("no robots.txt found — every crawler, AI or not, is allowed by default")
        return warnings
    star_groups = [g for g in doc.groups if g.has_agent("*")]
    for g in star_groups:
        if any(not r.allow and r.pattern in ("/", "*") for r in g.rules):
            warnings.append('blanket "Disallow: /" in the * group — every bot not listed '
                            "separately is blocked too, including future AI crawlers")
    for g in doc.groups:
        if g.crawl_delay is not None and g.crawl_delay > 30:
            warnings.append(f"crawl-delay of {g.crawl_delay:g}s for group "
                            f"({', '.join(g.agents[:3])}) — effectively a throttle-out")
    ai_blocked = [b["name"] for b in bots
                  if b["verdict"] == "BLOCKED" and b["kind"] != "baseline"]
    if ai_blocked and not star_groups:
        warnings.append("AI crawlers are blocked but there is no * group — "
                        "unlisted bots crawl freely; add a star group for a default policy")
    return warnings


def analyze(target: Optional[str], robots_text: Optional[str], missing: bool,
            probes: Optional[List[str]], bot_filter: Optional[List[str]]) -> Dict:
    """Full analysis -> report dict (returned by run())."""
    doc = parse(robots_text or "")
    probes_used = probes or DEFAULT_PROBES
    catalog = [c for c in CRAWLERS
               if not bot_filter or c["token"] in bot_filter]
    bots = [evaluate_bot(doc, c, probes_used) for c in catalog]

    blocked = sum(1 for b in bots if b["verdict"] == "BLOCKED")
    partial = sum(1 for b in bots if b["verdict"] == "PARTIAL")
    allowed = sum(1 for b in bots if b["verdict"] in ("ALLOWED", "DEFAULT"))

    report = {
        "target": target,
        "robots_url": robots_url(target) if target else "(local file)",
        "robots_present": not missing,
        "groups": len(doc.groups),
        "sitemaps": doc.sitemaps,
        "probes": probes_used,
        "summary": {
            "total_bots": len(bots),
            "blocked": blocked,
            "partial": partial,
            "allowed": allowed,
        },
        "bots": bots,
        "warnings": build_warnings(doc, missing, bots),
    }
    # HTTP-fetch override: a 404 body is empty text; force DEFAULT paths empty
    if missing:
        report["summary"] = {
            "total_bots": len(bots), "blocked": 0, "partial": 0, "allowed": len(bots),
        }
    return report


def run(target: Optional[str] = None, file: Optional[str] = None,
        timeout: float = 15.0, probes: Optional[List[str]] = None,
        bot_filter: Optional[List[str]] = None) -> Dict:
    """Main entrypoint: fetch (or load) robots.txt and analyze it."""
    if file:
        try:
            with open(file, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            raise RuntimeError(f"cannot read {file}: {exc}") from exc
        return analyze(None, text, False, probes, bot_filter)
    url = robots_url(target)
    status, text = fetch(url, timeout)
    if status == -1:
        raise RuntimeError(f"network error fetching {url}")
    missing = status == 404
    return analyze(target, text, missing, probes, bot_filter)


def render_text(report: Dict) -> str:
    """Human-readable report."""
    lines: List[str] = []
    head = report["target"] or report["robots_url"]
    lines.append(f"robotscope — AI crawler access report for {head}")
    lines.append("")
    if report["robots_present"]:
        lines.append(f"  robots.txt: {report['groups']} agent group(s), "
                     f"{len(report['sitemaps'])} sitemap(s)")
    else:
        lines.append("  robots.txt: MISSING — all crawlers allowed by default")
    lines.append("")
    lines.append(f"  {'BOT':<18} {'COMPANY':<14} {'TYPE':<9} "
                 f"{'VERDICT':<9} {'RULES FROM'}")
    for b in report["bots"]:
        src = {"own": "own group", "star": "fallback (*)",
               "none": "no policy"}.get(b["rules_from"], b["rules_from"])
        lines.append(f"  {b['name']:<18} {b['company']:<14} {b['kind']:<9} "
                     f"{b['verdict']:<9} {src}")
    s = report["summary"]
    lines.append("")
    lines.append(f"  {s['blocked']}/{s['total_bots']} blocked · "
                 f"{s['partial']} partial · {s['allowed']} allowed "
                 f"over {s['total_bots']} known AI & search crawlers")
    if report["warnings"]:
        lines.append("")
        for w in report["warnings"]:
            lines.append(f"  ⚠ {w}")
    return "\n".join(lines)


def render_json(report: Dict) -> str:
    return json.dumps(report, indent=2)
