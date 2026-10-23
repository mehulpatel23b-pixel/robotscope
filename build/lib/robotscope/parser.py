"""robots.txt parsing for robotscope.

Implements the practical superset of RFC 9309 that real sites deploy:
user-agent groups, Allow/Disallow rules with '*' and '$' wildcards,
Crawl-delay, and Sitemap directives. Directive and user-agent matching is
case-insensitive; rule precedence follows the Google/Bing convention of
longest-pattern-wins, with Allow winning exact ties.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

_DIRECTIVE_RE = re.compile(r"^\s*([a-zA-Z-]+)\s*:\s*(.*)$")


def strip_comment(line: str) -> str:
    """Remove a trailing '#...' comment (tolerating escaped '\\#')."""
    out, i = [], 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "#":
            out.append("#")
            i += 2
            continue
        if ch == "#":
            break
        out.append(ch)
        i += 1
    return "".join(out)


@dataclass
class Rule:
    allow: bool
    pattern: str

    @property
    def strength(self) -> int:
        """Effective specificity: pattern length without the '$' anchor."""
        return len(self.pattern[:-1] if self.pattern.endswith("$") else self.pattern)


@dataclass
class Group:
    agents: List[str] = field(default_factory=list)
    rules: List[Rule] = field(default_factory=list)
    crawl_delay: Optional[float] = None

    def has_agent(self, token: str) -> bool:
        return token.lower() in self.agents


@dataclass
class RobotsDoc:
    groups: List[Group] = field(default_factory=list)
    sitemaps: List[str] = field(default_factory=list)
    saw_directives: bool = False

    def rules_for(self, token: str) -> Tuple[List[Rule], Optional[float], str]:
        """Return (rules, crawl_delay, source) for a user-agent token.

        source: 'own'   -> a group names this token explicitly
                'star'  -> no named group; fell back to the '*' group
                'none'  -> no applicable rules at all (robots.txt default: allow)
        """
        token = token.lower()
        rules: List[Rule] = []
        delay = None
        for g in self.groups:
            if g.has_agent(token):
                rules.extend(g.rules)
                if g.crawl_delay is not None:
                    delay = g.crawl_delay
        if rules or delay is not None:
            return rules, delay, "own"
        for g in self.groups:
            if g.has_agent("*"):
                return g.rules, g.crawl_delay, "star"
        return [], None, "none"


def parse(text: str) -> RobotsDoc:
    doc = RobotsDoc()
    agents: List[str] = []
    rules: List[Rule] = []
    delay: Optional[float] = None

    def flush():
        if agents:
            doc.groups.append(Group(list(agents), list(rules), delay))

    for raw in text.replace("\r\n", "\n").split("\n"):
        line = strip_comment(raw).strip()
        if not line:
            continue
        m = _DIRECTIVE_RE.match(line)
        if not m:
            continue
        directive, value = m.group(1).lower(), m.group(2).strip()
        doc.saw_directives = True
        if directive == "user-agent":
            if rules or delay is not None:
                flush()
                rules, delay = [], None
                agents = []
            if value:
                agents.append(value.lower())
        elif directive == "allow":
            rules.append(Rule(True, value))
        elif directive == "disallow":
            rules.append(Rule(False, value))
        elif directive == "crawl-delay":
            try:
                delay = float(value)
            except ValueError:
                pass
        elif directive == "sitemap":
            if value:
                doc.sitemaps.append(value)
        # other directives (host, clean-param, ...) are recorded as seen but ignored
    flush()
    return doc


def match_path(path: str, pattern: str) -> bool:
    """Google-style wildcard match: '*' is anything, trailing '$' anchors the end.

    Patterns without a '$' anchor use prefix semantics, so 'Disallow: /blog'
    blocks '/blog' and everything under it.
    """
    if not pattern:
        return False
    anchored = pattern.endswith("$")
    base = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(part) for part in base.split("*"))
    if anchored:
        return re.fullmatch(regex, path) is not None
    return re.match(regex, path) is not None


def is_allowed(doc: RobotsDoc, token: str, path: str) -> Tuple[bool, str]:
    """Apply the ruleset for `token` to `path` -> (allowed, source)."""
    rules, _, source = doc.rules_for(token)
    if source == "none":
        return True, "none"
    best: Optional[Rule] = None
    for rule in rules:
        if match_path(path, rule.pattern):
            if best is None or rule.strength > best.strength or (
                rule.strength == best.strength and rule.allow
            ):
                best = rule
    if best is None:
        return True, source
    return best.allow, source
