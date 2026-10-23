# robotscope

**Audit your robots.txt against the AI-crawler gold rush — see exactly what GPTBot, ClaudeBot, Bytespider and 21 other bots are told to do on your site.**

![Python](https://img.shields.io/badge/Python-3.9%2B-000000?style=for-the-badge&logo=python&logoColor=00FF41)
![Tests](https://img.shields.io/badge/tests-53%2F53%20passing-000000?style=for-the-badge&logo=githubactions&logoColor=00FF41)
![Dependencies](https://img.shields.io/badge/dependencies-zero-000000?style=for-the-badge&logo=gnu-bash&logoColor=00FF41)
![License](https://img.shields.io/badge/license-MIT-000000?style=for-the-badge&logo=opensourceinitiative&logoColor=00FF41)

---

## Why this exists

AI crawler policy is now a real business decision, not a sysadmin footnote:

- **~45% of major websites** block at least one AI crawler, and Cloudflare flipped defaults so a growing share of the web blocks AI training bots outright
- Publishers split hairs between training bots (GPTBot, ClaudeBot, CCBot) and user-fetch agents (ChatGPT-User, Perplexity-User) — block one, keep the other, and the robots.txt to do it is fiddly
- **An estimated 27% of sites block AI crawlers *accidentally***, through a stray blanket `Disallow: /` or an over-eager `*` group — silently disappearing from AI answers
- Doing this by hand means tracing 60+ user-agent groups, wildcard patterns and `Crawl-delay` values across 24 bots — every time you ship a deploy

`robotscope` turns that from a 2-hour log yelling into a one-command verdict, with warnings for the classic foot-guns before they cost you AI-search visibility.

## Install

```bash
# straight from GitHub
pip install git+https://github.com/mehulpatel23b-pixel/robotscope.git

# or from source
git clone https://github.com/mehulpatel23b-pixel/robotscope.git
cd robotscope
pip install .
```

Zero third-party dependencies — Python 3.9+ stdlib only (urllib, argparse, dataclasses). Also usable without installing:

```bash
python -m robotscope --help
```

## Quickstart

```bash
# audit any site (https:// added automatically)
robotscope example.com

# restrict to the OpenAI policy
robotscope example.com --bot GPTBot,OAI-SearchBot,ChatGPT-User

# probe paths you actually care about
robotscope example.com --paths /,/articles/,/feed.xml

# machine-readable
robotscope example.com --json

# audit a local file (no network needed)
robotscope -f config/robots-production.txt

# CI gate: fail the build if AI bots got blocked
robotscope example.com --fail-if-blocked GPTBot,ClaudeBot,PerplexityBot
```

## Sample output (real sites, verified)

```
$ robotscope https://www.nytimes.com

robotscope — AI crawler access report for https://www.nytimes.com

  robots.txt: 63 agent group(s), 25 sitemap(s)

  BOT                COMPANY        TYPE      VERDICT   RULES FROM
  GPTBot             OpenAI         training  BLOCKED   own group
  OAI-SearchBot      OpenAI         search    BLOCKED   own group
  ChatGPT-User       OpenAI         agent     BLOCKED   own group
  ClaudeBot          Anthropic      training  BLOCKED   own group
  ...
  Googlebot          Google         baseline  ALLOWED   own group
  Amazonbot           Amazon         training  ALLOWED   own group
  ...

  19/24 blocked · 0 partial · 5 allowed over 24 known AI & search crawlers
```

And the GitHub open policy for contrast (real output):

```
$ robotscope github.com

  GPTBot             OpenAI         training  ALLOWED   own group
  ClaudeBot          Anthropic     training  ALLOWED   own group
  Bytespider         ByteDance      training  BLOCKED   own group  ← sorry, ByteDance
```

**Verdicts**

| Verdict        | Meaning                                                        |
|----------------|----------------------------------------------------------------|
| `BLOCKED`      | every probed path is disallowed for this bot                   |
| `PARTIAL`      | some paths blocked, some allowed                               |
| `ALLOWED`      | a ruleset exists and nothing probed is blocked                 |
| `DEFAULT`      | no rules apply at all — robots.txt allows everything by default |

**Report columns** — `RULES FROM` tells you where the verdict comes from: `own group` (this bot is named explicitly), `fallback (*)` (bot inherits the `*` group's policy — often unintentional), `no policy` (nothing applies; everything allowed).

## The catalog

24 crawler user-agents, grouped by intent:

| Type            | Bots                                                                |
|-----------------|---------------------------------------------------------------------|
| `training`      | GPTBot, ClaudeBot, CCBot, Google-Extended, Applebot-Extended, Amazonbot, meta-externalagent, Bytespider, cohere-ai, Diffbot, Omgilibot, img2dataset |
| `search`        | OAI-SearchBot, Claude-SearchBot, PerplexityBot, DuckAssistBot, YouBot |
| `agent`         | ChatGPT-User, Claude-Web, Perplexity-User                           |
| `baseline`      | Googlebot, bingbot, Applebot, FacebookBot (classic web search, for contrast) |

The catalog lives in `src/robotscope/crawlers.py` — adding a newly-announced AI crawler is a 1-line entry.

## How matching works

robotscope implements the Google/Bing/RFC 9309 convention used by the big crawlers:

- **User-agent groups** — consecutive `User-agent:` lines share one rule block; groups apply case-insensitively by token
- **Prefix semantics** — `Disallow: /blog` blocks `/blog`, `/blog/post`, and yes, `/blogg`
- **Longest rule wins** — `Allow: /blog/public/` defeats `Disallow: /blog/` (say that three times fast)
- **Ties go to Allow** — equal-length Allow and Disallow rules allow the path
- **Wildcards** — `*` matches anything, `$` anchors the end (`Disallow: /*.pdf$`)
- **`*` group fallback** — a bot with no named group inherits the `*` group; robotscope reports this as `fallback (*)` so you notice accidental inheritance
- **No rules at all** — allowed by default (RFC 9309), reported as `DEFAULT`
- Empty `Disallow:` = allow all; `Crawl-delay` and `Sitemap` parsed per group

## Exit codes

| Code | Meaning                                                             |
|------|----------------------------------------------------------------------|
| `0`  | analysis completed (verdicts may still say BLOCKED — that's the point) |
| `1`  | network / fetch / file error                                         |
| `2`  | CI gate tripped — a bot from `--fail-if-blocked` is BLOCKED          |

## Architecture

```
┌─────────────┐   fetch (urllib)   ┌──────────────┐
│  CLI / api  │ ─────────────────► │ robots.txt   │
│  cli.py     │                    │ checker.py   │
└──────┬──────┘                    └──────┬───────┘
       │                                  │ parse
       │                                  ▼
       │                           ┌──────────────┐
       │  24-bot catalog           │ parser.py    │
       │  crawlers.py ────────────►│ groups, rules│
       │                           │ wildcards, $ │
       │                           └──────┬───────┘
       │ probe paths                       │ is_allowed()
       ▼                                  ▼
  report dict ──── render_text / render_json ──── stdout
```

Data flow: `run()` fetches (or reads) the robots.txt → `parser.parse()` produces a `RobotsDoc` of `Group`s and `Rule`s → `evaluate_bot()` probes each catalog bot against `DEFAULT_PROBES` paths → `build_warnings()` flags policy foot-guns → CLI renders text or JSON and evaluates the CI gate.

## Project structure

```
robotscope/
├── src/robotscope/
│   ├── __init__.py      # public API: run, render_text, render_json
│   ├── __main__.py      # python -m robotscope
│   ├── parser.py        # robots.txt → Groups/Rules, wildcard matcher
│   ├── crawlers.py      # 24-bot AI crawler catalog
│   ├── checker.py       # fetch, evaluate, warnings, report building
│   └── cli.py           # argparse interface, exit-code policy
├── tests/
│   └── test_robotscope.py   # 53 tests, no network required
├── pyproject.toml
├── requirements.txt
├── LICENSE
└── README.md
```

## Real-world use cases

1. **Release checklist** — run `robotscope yoursite.com` before and after your robots.txt changes ship; the diff between the two verdict tables *is* the policy change, readable by a PM in 10 seconds
2. **CI policy gate** — `--fail-if-blocked GPTBot,ClaudeBot,PerplexityBot`in your deploy pipeline catches the classic "someone added a blanket Disallow and now we vanished from AI answers" regression
3. **SEO/AEO monitoring** — scheduled cron against your production domain; a config upload that silently flips your AI-crawler policy changes the JSON output and trips your diff tooling
4. **Competitive intelligence** — audit competitors' AI policies before pricing an AI-visibility strategy: who allows GPTBot? who blocks Bytespider only? (all public data, this just aggregates it)
5. **Publisher licensing prep** — negotiating with an AI company? pull the counterparty's user-agent from their blog post, probe it directly via `--bot`, and confirm your own site says what your legal team thinks it says
6. **WAF/CDN migration audits** — moving to Cloudflare (whose 2026 defaults block AI training bots) or a new host? Compare `robotscope old-host.com` vs the new deployment before you cut traffic over
7. **Agent scraping hygiene** — building an AI agent or scraper that respects robots.txt? Use `is_allowed(doc, "MyAgent/1.0", path)` from the parser as the library-level gate before fetches

## Honesty section

- robotscope reads **robots.txt only** — it does not (and cannot) see X-Robots-Tag headers, Cloudflare/CDN bot-management blocks, IP blocks or JS walls, which can block crawlers regardless of robots.txt. Treat it as the declarative-policy layer, not the whole gate.
- Verdicts are probes over representative paths, not a full-site crawl; a `PARTIAL` verdict on default probes doesn't tell you about your 40,000 private product pages.
- The crawler catalog is a maintained snapshot, not a live registry. Unknown user-agents still work: pass them via `--bot` (anything unlisted falls back to the `*` group like real crawlers do).

## License

MIT — see [LICENSE](LICENSE).
