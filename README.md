## Overview

Today, code changes live in diffs, commits, and pull requests. They are optimized for machines and developers, but invisible or confusing to everyone else.

**Cartero changes that.**

It turns any code change into something that can be **executed, understood, and communicated. Automatically**.

From a single git diff, Cartero generates structured outputs that explain:

* What changed
* Why it matters
* What users can now do

And this is just the beginning.

Cartero is evolving into a system where every code change becomes a complete communication package, including changelogs, FAQs, and product marketing content, ready to publish.

Not just updating a repository.
Not just generating commits.

**Cartero turns code into communication.**

---

## Roadmap

Cartero is evolving from a commit tool into a full system for turning code into communication.

### What exists today

* Generate structured commit summaries from git diffs (`cartero generate`)
* Generate product-style changelog entries with real-time streaming (`cartero changelog`)
* Generate a session brief from the master context, ready to paste into any LLM (`cartero session`)
* Stage files and create git commits in plain language (`cartero commit`)
* Append quick repo-local session notes for commit context (`cartero note`)
* Compress raw notes or LLM conversations into structured context (`cartero context`)
* Validate and execute structured change summaries safely (`cartero run`)
* Optional context support — provide notes or conversations to improve output quality
* Multi-provider LLM support (Anthropic and Gemini)

When `cartero commit` runs without `--context-file`, it now checks `.cartero/session-notes.md` first and uses those notes as raw commit context when present.

### What’s coming next

* Generate complete documentation packages (changelog, FAQ, marketing) from a single diff
* Clean and manage generated outputs automatically
* Push changes and publish updates to GitHub without manual steps

### Where this is going

* Every code change becomes instantly understandable
* Every update is ready to share with users
* The gap between building and communicating software disappears

---

## Local LLM Setup

Cartero uses Anthropic by default for live LLM generation.

Set `ANTHROPIC_API_KEY` in your shell before running live generation or integration tests:

```bash
export ANTHROPIC_API_KEY=your_key_here
```

To persist it in `zsh`, add the same line to `~/.zshrc` and reload your shell.

Integration tests marked with `integration` skip when `ANTHROPIC_API_KEY` is not configured.
Missing credentials now fail fast with a configuration error instead of falling back to a fake key.

## Readiness Harness

Run the curated readiness corpus with:

```bash
cartero readiness
```

The command prints a JSON report with one entry per case plus an aggregate summary.
Use `summary.total_cases`, `summary.fail_level_count`, and `summary.warn_level_count` for the headline signal.
Use `summary.fallback_frequency`, `summary.retry_frequency`, and `summary.normalization_frequency` to see how often the current pipeline had to lean on safety rails.
Use `summary.parity` to confirm the structured `commit_fields` still align with YAML-backed behavior and the web/CLI surfaces.

The command exits with code `1` when the report contains fail-level cases or parity mismatches, so it can be used as a lightweight gating check.
# note flow test
