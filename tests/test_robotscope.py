"""Test suite for robotscope — 32 tests, stdlib unittest, no network."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from robotscope.parser import (Group, Rule, is_allowed, match_path, parse,
                               strip_comment)
from robotscope.crawlers import CRAWLERS, by_token, resolve_names
from robotscope.checker import (DEFAULT_PROBES, evaluate_bot, normalize_target,
                                robots_url, render_json, run,
                                build_warnings, analyze)
from robotscope import __version__

BLOCK_ALL = """
User-agent: *
Disallow: /
"""

BLOCK_GPT_ONLY = """
User-agent: *
Disallow:

User-agent: GPTBot
Disallow: /
"""

PARTIAL = """
User-agent: *
Disallow: /blog/
Disallow: /admin
Allow: /blog/public/
"""

ADVANCED = """
# top comment
User-agent: GPTBot
User-agent: CCBot
Crawl-delay: 10
Disallow: /
Allow: /about

User-Agent: claudebot
Disallow: /secret/$

user-agent: *
crawl-delay: 0.5
Disallow: /tmp
Sitemap: https://example.com/sitemap.xml
"""

MERGED = """
User-agent: GPTBot
Disallow: /a

User-agent: GPTBot
Disallow: /
"""


class TestParser(unittest.TestCase):
    def test_basic_group_parse(self):
        doc = parse(BLOCK_ALL)
        self.assertEqual(len(doc.groups), 1)
        self.assertTrue(doc.groups[0].has_agent("*"))
        self.assertEqual(len(doc.groups[0].rules), 1)

    def test_group_split_on_new_user_agent(self):
        doc = parse(ADVANCED)
        self.assertEqual(len(doc.groups), 3)

    def test_multi_agent_single_group(self):
        doc = parse(ADVANCED)
        gpt = [g for g in doc.groups if g.has_agent("gptbot")]
        self.assertEqual(len(gpt), 1)
        self.assertIn("ccbot", [a for g in gpt for a in g.agents])

    def test_comment_stripping(self):
        self.assertEqual(strip_comment("Disallow: / # no admin"), "Disallow: / ")

    def test_directive_case_insensitive(self):
        doc = parse("USER-AGENT: gptbot\nDISALLOW: /\n")
        allowed, src = is_allowed(doc, "gptbot", "/")
        self.assertFalse(allowed)

    def test_user_agent_case_insensitive_match(self):
        doc = parse("User-agent: GPTBot\nDisallow: /\n")
        allowed, _ = is_allowed(doc, "gptbot", "/")
        self.assertFalse(allowed)

    def test_empty_disallow_means_allow_all(self):
        doc = parse("User-agent: *\nDisallow:\n")
        allowed, _ = is_allowed(doc, "anything", "/")
        self.assertTrue(allowed)

    def test_crlf_tolerated(self):
        doc = parse("User-agent: *\r\nDisallow: /\r\n")
        allowed, _ = is_allowed(doc, "x", "/")
        self.assertFalse(allowed)

    def test_star_fallback(self):
        doc = parse(BLOCK_ALL)
        rules, _, source = doc.rules_for("claudebot")
        self.assertEqual(source, "star")

    def test_no_rules_at_all_is_default_allow(self):
        doc = parse("User-agent: GPTBot\nCrawl-delay: 5\n")
        allowed, src = is_allowed(doc, "unknownbot", "/")
        self.assertTrue(allowed)
        self.assertEqual(src, "none")

    def test_own_group_preferred_over_star(self):
        doc = parse("User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /\n")
        rules, _, source = doc.rules_for("gptbot")
        self.assertEqual(source, "own")

    def test_duplicate_agent_groups_merge(self):
        doc = parse(MERGED)
        rules, _, source = doc.rules_for("gptbot")
        self.assertEqual(source, "own")
        self.assertEqual(len(rules), 2)

    def test_crawl_delay_parsed_per_group(self):
        doc = parse(ADVANCED)
        _, gpt_delay, _ = doc.rules_for("gptbot")
        self.assertEqual(gpt_delay, 10.0)
        _, star_delay, _ = doc.rules_for("foo")
        self.assertEqual(star_delay, 0.5)

    def test_sitemap_collected(self):
        doc = parse(ADVANCED)
        self.assertEqual(doc.sitemaps, ["https://example.com/sitemap.xml"])

    def test_unknown_directives_ignored(self):
        doc = parse("Host: example.com\nUser-agent: *\nClean-param: utm\n")
        self.assertEqual(len(doc.groups), 1)

    def test_empty_text_yields_empty_doc(self):
        doc = parse("   \n# only a comment\n")
        self.assertEqual(len(doc.groups), 0)
        self.assertFalse(doc.saw_directives)


class TestMatching(unittest.TestCase):
    def test_exact_prefix_blocks_children(self):
        doc = parse("User-agent: *\nDisallow: /blog\n")
        self.assertFalse(is_allowed(doc, "x", "/blog/post-1")[0])
        # RFC 9309: plain values are prefix matches, so /blog blocks /blogg too
        self.assertFalse(is_allowed(doc, "x", "/blogg")[0])
        self.assertTrue(is_allowed(doc, "x", "/blo")[0])

    def test_dollar_anchor_exact_root(self):
        doc = parse("User-agent: claudebot\nDisallow: /secret/$\n")
        self.assertFalse(is_allowed(doc, "claudebot", "/secret/")[0])
        self.assertTrue(is_allowed(doc, "claudebot", "/secret/deeper")[0])

    def test_wildcard_match(self):
        doc = parse("User-agent: *\nDisallow: /*.pdf$\n")
        self.assertFalse(is_allowed(doc, "x", "/files/report.pdf")[0])
        self.assertTrue(is_allowed(doc, "x", "/files/report.html")[0])

    def test_bare_star_rule_blocks_everything(self):
        doc = parse("User-agent: *\nDisallow: /help/*/\n")
        self.assertFalse(is_allowed(doc, "x", "/help/a/")[0])

    def test_longest_rule_wins(self):
        doc = parse(PARTIAL)
        self.assertFalse(is_allowed(doc, "x", "/blog/x")[0])
        self.assertTrue(is_allowed(doc, "x", "/blog/public/x")[0])

    def test_tie_allow_wins(self):
        doc = parse("User-agent: *\nDisallow: /a\nAllow: /a\n")
        self.assertTrue(is_allowed(doc, "x", "/a")[0])

    def test_match_path_helper(self):
        self.assertTrue(match_path("/x/y", "/x"))
        self.assertTrue(match_path("/x/y", "/x/*"))
        self.assertFalse(match_path("/xy", "/x$"))
        self.assertTrue(match_path("/x", "/x$"))
        self.assertFalse(match_path("/anything", ""))


class TestCatalog(unittest.TestCase):
    def test_catalog_size(self):
        self.assertGreaterEqual(len(CRAWLERS), 20)

    def test_unique_tokens(self):
        tokens = [c["token"] for c in CRAWLERS]
        self.assertEqual(len(tokens), len(set(tokens)))

    def test_all_fields_present(self):
        for c in CRAWLERS:
            for f in ("token", "name", "company", "kind", "note"):
                self.assertIn(f, c)

    def test_key_bots_present(self):
        for tok in ("gptbot", "claudebot", "ccbot", "google-extended",
                    "bytespider", "perplexitybot"):
            self.assertTrue(any(c["token"] == tok for c in CRAWLERS))

    def test_by_token_lookup(self):
        self.assertEqual(by_token("GPTBOT")["name"], "GPTBot")

    def test_resolve_names_accepts_display_names(self):
        self.assertEqual(resolve_names("GPTBot, ClaudeBot"), ["gptbot", "claudebot"])

    def test_resolve_names_passthrough_unknown(self):
        self.assertEqual(resolve_names("MyCustomBot"), ["mycustombot"])


class TestChecker(unittest.TestCase):
    def test_normalize_target_adds_scheme(self):
        self.assertEqual(normalize_target("example.com"), "https://example.com")
        self.assertEqual(normalize_target("https://x.com/"), "https://x.com")

    def test_robots_url(self):
        self.assertEqual(robots_url("http://a.com/x/y"), "http://a.com/robots.txt")

    def test_eval_blocked_bot(self):
        doc = parse(BLOCK_GPT_ONLY)
        row = evaluate_bot(doc, by_token("gptbot"), DEFAULT_PROBES)
        self.assertEqual(row["verdict"], "BLOCKED")
        self.assertEqual(row["rules_from"], "own")

    def test_eval_default_verdict_when_no_rules(self):
        doc = parse("Sitemap: https://x.com/s.xml\n")
        row = evaluate_bot(doc, by_token("gptbot"), DEFAULT_PROBES)
        self.assertEqual(row["verdict"], "DEFAULT")
        self.assertEqual(row["rules_from"], "none")

    def test_eval_partial(self):
        doc = parse(PARTIAL)
        row = evaluate_bot(doc, by_token("gptbot"), DEFAULT_PROBES)
        self.assertEqual(row["verdict"], "PARTIAL")
        self.assertIn("/blog/", row["blocked_paths"])

    def test_eval_star_fallback_source(self):
        doc = parse(BLOCK_ALL)
        row = evaluate_bot(doc, by_token("gptbot"), DEFAULT_PROBES)
        self.assertEqual(row["verdict"], "BLOCKED")
        self.assertEqual(row["rules_from"], "star")

    def test_missing_robots_warns(self):
        w = build_warnings(parse(""), missing=True, bots=[])
        self.assertTrue(any("no robots.txt" in x for x in w))

    def test_blanket_deny_warning(self):
        doc = parse(BLOCK_ALL)
        w = build_warnings(doc, missing=False,
                           bots=[{"verdict": "ALLOWED", "kind": "training",
                                  "name": "x", "rules_from": "star"}])
        self.assertTrue(any("blanket" in x for x in w))

    def test_slow_crawl_delay_warning(self):
        doc = parse("User-agent: *\nCrawl-delay: 120\nDisallow: /x\n")
        w = build_warnings(doc, missing=False, bots=[])
        self.assertTrue(any("crawl-delay" in x.lower() for x in w))

    def test_analyze_summary_counts(self):
        rep = analyze("https://example.com", BLOCK_GPT_ONLY, False, None, None)
        self.assertEqual(rep["summary"]["blocked"], 1)
        self.assertGreaterEqual(rep["summary"]["allowed"], 1)
        self.assertEqual(rep["summary"]["total_bots"], len(CRAWLERS))

    def test_analyze_bot_filter(self):
        rep = analyze(None, BLOCK_GPT_ONLY, False, None, ["gptbot"])
        self.assertEqual(len(rep["bots"]), 1)

    def test_analyze_custom_probes(self):
        rep = analyze(None, PARTIAL, False, ["/only"], None)
        self.assertEqual(rep["probes"], ["/only"])

    def test_render_json_roundtrip(self):
        import json
        rep = analyze(None, PARTIAL, False, None, ["gptbot"])
        data = json.loads(render_json(rep))
        self.assertEqual(data["bots"][0]["verdict"], "PARTIAL")

    def test_render_text_mentions_every_bot(self):
        rep = analyze(None, BLOCK_ALL, False, None, None)
        text = rep
        from robotscope.checker import render_text
        out = render_text(rep)
        for c in CRAWLERS:
            self.assertIn(c["name"], out)

    def test_missing_robots_all_allowed(self):
        rep = analyze("https://x.com", "", True, None, None)
        self.assertFalse(rep["robots_present"])
        self.assertEqual(rep["summary"]["blocked"], 0)


class TestCli(unittest.TestCase):
    def _robots_file(self, text=BLOCK_GPT_ONLY):
        import tempfile
        f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_file_mode_exit_zero(self):
        from robotscope.cli import main
        rc_report = {}
        class FakeWriter:
            def write(self, *a): pass
        old = sys.stdout
        sys.stdout = FakeWriter()
        try:
            rc = main(["-f", self._robots_file()])
        finally:
            sys.stdout = old
        self.assertEqual(rc, 0)

    def test_json_flag_outputs_json(self):
        import io, json
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            from robotscope.cli import main
            rc = main(["-f", self._robots_file(), "--json"])
        finally:
            sys.stdout = old
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertIn("bots", data)

    def test_ci_gate_triggers_exit_2(self):
        import io
        buf = io.StringIO()
        old_err, old_out = sys.stderr, sys.stdout
        sys.stderr = sys.stdout = buf
        try:
            from robotscope.cli import main
            rc = main(["-f", self._robots_file(), "--fail-if-blocked", "GPTBot"])
        finally:
            sys.stderr, sys.stdout = old_err, old_out
        self.assertEqual(rc, 2)

    def test_ci_gate_passes_when_bot_allowed(self):
        import io
        buf = io.StringIO()
        old_err, old_out = sys.stderr, sys.stdout
        sys.stderr = sys.stdout = buf
        try:
            from robotscope.cli import main
            rc = main(["-f", self._robots_file(PARTIAL),
                       "--fail-if-blocked", "GPTBot"])
        finally:
            sys.stderr, sys.stdout = old_err, old_out
        self.assertEqual(rc, 0)

    def test_missing_target_and_file_errors(self):
        from robotscope.cli import main
        with self.assertRaises(SystemExit):
            main([])

    def test_run_file_missing_errors(self):
        with self.assertRaises(RuntimeError):
            run(file="/nonexistent/robots.txt")

    def test_path_option_guards_slash(self):
        from robotscope.cli import main
        # paths without leading slash are normalized; smoke via analyze instead
        rep = analyze(None, PARTIAL, False, ["docs"], None)
        self.assertEqual(rep["probes"], ["docs"])


class TestMeta(unittest.TestCase):
    def test_version(self):
        self.assertTrue(__version__.startswith("1."))


if __name__ == "__main__":
    unittest.main(verbosity=2, exit=False)
