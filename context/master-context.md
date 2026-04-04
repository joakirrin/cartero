# Cartero – Master Context
_Last updated: 2026-04-04 18:45_
_File path: `context/master-context.md`_

## 1. Product Identity & Core Insight

### What Cartero Is
Cartero is a system that turns code changes into structured, reusable communication across multiple outputs (commit summaries, changelogs, FAQs, knowledge bases, and product updates).

It evolves from a YAML validation tool into an AI-assisted change orchestration and documentation system for vibe coders and non-technical users.

### Core Differentiation
- diff explains what changed  
- context explains why it matters  
- combining both produces significantly higher-quality outputs  

Cartero is not a commit generator.  
It is a communication system.

---

## 2. Hard Rules (Non-Negotiable)

### Output Rules
- LLM returns structured plain-text using custom delimiter markers, and the system parses it into internal structured data before generating final outputs
- Never invent actions or changes not present in diff/context
- Never include lock files, generated files, or file content exceeding 500 characters

### Tone Rules
- Write for both humans and LLMs
- Product release note style (Notion / Linear)
- Summary must start with “Cartero”
- Do not use git verbs (fix, refactor, chore, update, patch)

### System Rules
- diff is the source of truth (what changed)
- context provides intent (why it matters)
- context is optional but improves output quality

### Architecture Rules
- CLI parity with web is mandatory for all features

---

## 3. Current Capabilities (Implemented)

- Validate YAML summaries
- Simulate execution (`--dry-run`)
- Apply changes (`--apply`)
- Generate summaries from git diffs (`cartero generate`)
- Automatic git diff detection (no stdin required)
- Accept optional context via `--context-file`
- Compress raw context into structured recap (`cartero context`)
- Stage files and generate commits (`cartero commit`)
- Interactive file selection for commits
- Plain-language PMM-style summaries
- Retry LLM calls with stricter prompt on failure
- Split large diffs into per-file chunks
- Merge chunked outputs
- Propagate warnings to CLI and web
- Multi-provider LLM support (Anthropic + Gemini)
- [Phase 4.5 implemented but not yet validated: optional --context-file for generate and commit, cartero context command, structured recap generation, recap + diff as combined LLM input, auto-detection of git diff]
- Defined the Phase 5 canonical documentation contract for commit summaries, changelogs, FAQs, and knowledge base entries
- Defined the canonical record as the shared internal data model for documentation outputs
- Defined the transformation specification from diff + context into canonical Cartero records
- Defined the output/render layer for deterministic reuse of canonical records across output surfaces
- Defined the Codex prompt bridge structure for converting canonical records into agent-ready instructions
- Established a sequential prompting strategy: contract -> transformation -> output layer
- Generate product-style changelog entries from git diffs (`cartero changelog`)
- Real-time streaming output for changelog generation (Anthropic provider)
- Phase 4.5 validated with real API calls and real diffs
- Generate a session brief from the master context (`cartero session`) — ready to paste into any LLM to start a working session with full project context
- Generate changelog entries from diff via web (POST /api/changelog)
- Retrieve session brief via web (GET /api/session)
- Guided 4-step wizard interface at /wizard for non-technical users

---

## 4. Current Priorities (Active Now)

1. ✅ Phase 4.5 validated — Context-Aware Generation confirmed working with real API and real diffs
2. Web interface parity — every CLI command must have an equivalent web endpoint. Currently missing: `cartero changelog`, `cartero session`. This is a non-negotiable architectural rule.
3. Documentation Package (Phase 5)
4. GitHub Integration (Phase 6)
5. Guided CLI Flow (Phase 6.5)
6. UX / Flow Simplification
7. Repository & Presentation Layer
8. File Management (Deprioritized)

---

## 5. System Behavior (How Cartero Works)

### Inputs
- git diff (required)
- context (optional)

### Context Processing
Raw context is compressed into a structured recap:

- goal  
- user problem  
- decisions  
- tradeoffs  
- user impact  

### Generation Flow

1. Process context (if provided)
2. Combine recap + diff
3. Diff remains source of truth
4. Apply the canonical documentation contract
5. Transform diff + recap into a canonical Cartero record
6. Parse fields in-memory using regex
7. Render final output format from the canonical record
8. Validate output

Context enhances quality but never overrides the diff.

---

## 6. Architecture

### LLM Pipeline
- receive diff
- optional context
- context → recap
- split into chunks if needed
- LLM per chunk
- merge results
- apply canonical contract
- transform diff + context into canonical record
- parse fields in-memory with regex
- validate
- render output surfaces from canonical record
- derive Codex prompt bridge when needed

### Documentation System Layers
- canonical contract layer — schema, field semantics, and delimiter rules
- transformation layer — diff + context → canonical record
- output/render layer — canonical record → commit summary, changelog, FAQ, knowledge base
- agent bridge layer — canonical record → Codex instructions

### Key Decision

LLM produces structured plain-text with custom markers, which is parsed into a canonical record used as the internal source of truth.
The canonical record is the single source of truth for all output surfaces.
The system parses the response in-memory and controls final output formatting.

[Current implementation still uses JSON → YAML via CarteroDumper. Migration to plain-text delimiter format is part of Phase 5. Do not revert CarteroDumper until the canonical contract is fully defined and validated.]

### Principle
Every CLI function must have an equivalent web interface.

---

## 7. Known Issues / Constraints

- JSON output replaced with plain-text delimiter format to eliminate parse instability across generation flows. LLM returns structured plain-text with custom markers as a canonical record, parsed in-memory with regex. Resilient to LLM formatting errors and pairs well with streaming for the web UI.

- System correctness depends on strict adherence to the canonical delimiter format
  → malformed records remain a failure risk without stronger validation enforcement

- Prompt quality depends on keeping the canonical contract read-only
  → LLM drift can degrade consistency if the contract is rewritten or loosely interpreted

- Output quality still needs improvement  
  → summaries should be shorter and more product-like  

- Automatic validation of canonical records is not yet fully enforced
  → malformed records may still pass too far through the pipeline

- Context input still has friction (file-based)  
  → future improvement: inline or guided input  

- CLI requires multiple commands for full workflow  
  → will be simplified via interactive mode  

- Streaming is handled inside llm.py rather than the CLI layer — architecturally not ideal but preserves the existing test suite without modification
- test_changelog.py lives in the repo root — should be moved to tests/ or removed before production
- Step 3 wizard UI labels ("Updating GitHub", "Updating project context") are cosmetic and do not reflect real backend calls. Must be corrected before Phase 6 connects real GitHub operations — labels must only appear when the corresponding action is actually executing
- Phase 6 must include a success state that confirms changes were applied and that the new logs are visible on GitHub
- Phase 6 must include an error state that surfaces the actual error message from a failed GitHub upload — silent failure is not acceptable

---

## 8. Open Decisions / Pending Validation

- Validation layer design:
  - how strictly to enforce canonical record compliance
  - where to stop malformed records in the pipeline
  - [Sanitization layer design: a sanitization pass must run before regex parsing to detect and handle cases where the LLM hallucinates delimiter closure or embeds delimiter markers inside content (e.g. when discussing code). If the canonical record is malformed at parse time, the entire output chain — GitHub, web, CLI — fails silently. Sanitization must be designed as part of the canonical contract in Phase 5, not as a post-hoc patch. Risk level: high.]

- Stress testing strategy:
  - noise-only diffs
  - ambiguous diffs
  - large multi-change diffs

- External integrations:
  - Notion (knowledge base / marketing)
  - Docusaurus / GitHub Pages (docs + FAQ)
  - Support bots / knowledge hubs
  - Gamma (presentations, later phase)

- Prompting strategy:
  - how strictly to enforce sequential prompting across contract, transformation, and output stages
  - where single-prompt generation remains acceptable

- Best UX for context input:
  - file-based vs inline vs guided CLI

- Guided CLI flow design:
  - how much structure vs flexibility

---

## 9. Roadmap (Full)

### Phase 4.8 — Web Interface Parity

- ✅ Phase 4.8 — Web Interface Parity
- POST /api/changelog endpoint (accepts diff + optional context, returns changelog as JSON)
- GET /api/session endpoint (returns session brief from master-context.md as JSON)
- Flask server starts correctly via if __name__ == "__main__"
- 89 tests passing (baseline was 48)

### Phase 5 — Documentation Package

- ✅ Phase 5.1 — Wizard Web Interface
- /wizard route implemented in web.py
- cartero/templates/wizard.html — self-contained single-page wizard
- 4-step guided flow: review changes → add context → generate → done
- Integrates with POST /api/changelog and GET /api/session
- Detects git diff automatically; shows correct state (changes/no changes)
- Known bug: /api/session called 3x on Step 4 load — needs fix
- Pending: full flow test with real diff, copy prompt button test
- ✅ First output surface implemented: `cartero changelog` generates product-style changelog entries from git diffs with optional context and real-time streaming output
- ✅ POST /api/changelog web endpoint implemented (accepts diff + optional context, returns changelog)
- ✅ GET /api/session web endpoint implemented (returns session brief from master-context.md)
- Improve output quality toward product-style communication (Notion / Linear level)
- Standardize output structure and formatting
- Ensure consistency across:
  - commit summaries
  - changelogs
  - FAQs
  - knowledge base entries
- Introduce reusable templates for different output types
- Replace JSON output with plain-text delimiter format — use structured plain-text with custom markers instead of JSON. Parse fields with regex in-memory. Eliminates parse failures across all generation flows and unblocks reliable output for GitHub integration, guided CLI, and web UI.
- [Migration to plain-text delimiter format is a hard prerequisite for the Documentation Package. Do not attempt multi-output generation over the current JSON/YAML pipeline — JSON is too rigid for extended marketing and FAQ text blocks and will cause token overflow and escape errors. The canonical contract must be defined and validated before any output surface is built on top of it.]

### Phase 6 — GitHub Integration

- Integrate Cartero into pull request workflows
- Automatically generate outputs from PR diffs
- Post Cartero outputs as PR comments
- Enable usage within existing developer workflows without friction

### Phase 6.5 — Guided CLI Flow

- Introduce an interactive CLI experience
- Reduce need for multiple manual commands
- Provide step-by-step guidance
- Suggest next actions based on context
- Improve onboarding experience
- [Detect ambiguous diffs and actively prompt the user for context when the diff alone is insufficient to produce a meaningful summary. Context remains optional by design for adoption reasons, but the system should never silently generate low-quality output when it can detect that context would materially improve it.]

### Phase 7 — UX / Flow Simplification

- Reduce friction in context input
- explore inline input
- guided prompts
- Improve output readability
- Introduce smart defaults
- Minimize required user decisions

### Phase 8 — Repository & Presentation Layer

- Enable publishing outputs to:
  - Notion
  - documentation systems
  - knowledge bases
- Create a “presentation-ready” layer
- Support structured export formats

### Phase 12 — Vibe Coding Course

- Extract the Cartero development methodology into a structured course
- Content sourced from real documented sessions using Cartero itself
- Covers: prompt design, LLM-assisted decisions, step-by-step verification, context management, and the full vibe coding loop
- Cartero documents its own teaching method

### Phase X — Context Automation & Vibe Loop

Introduce a system that continuously aligns product context, communication, and LLM workflows with real development activity.

#### X.1 — Work Session Capture

- Automatically detect code changes (diff)
- Accept optional developer notes
- Generate structured work-session summaries

#### X.2 — Master Context Update Engine

- Compare work-session summary with master-context.md
- Propose updates (never auto-apply)
- Detect:
  - capability changes
  - priority shifts
  - resolved or new issues

#### X.3 — Derived Files Regeneration

- Regenerate:
  - llm-project-instructions.md
  - user-instructions.candidate.md
- Ensure consistency with master context

#### X.4 — Validation Engine

- Validate refreshed files against master context
- Output:
  - PASS
  - PASS WITH WARNINGS
  - FAIL
- Block promotion if validation fails

#### X.5 — Approval Layer

- Require human approval for:
  - updates to master-context.md
  - promotion of user instructions
- Enable feedback loop on rejected proposals

#### X.6 — Context State Management

- Introduce:
  - context/system-state.md
- Tracks:
  - last successful refresh
  - validation status
  - pending proposals
  - active instruction version

#### X.7 — LLM Session Bootstrap

- Generate ready-to-use prompts for:
  - ChatGPT
  - Claude
  - Codex
- Include:
  - current priorities
  - recent changes
  - relevant context

#### X.8 — Priority Intelligence (Future)

- Detect implicit roadmap or priority changes
- Propose updates with confidence levels
- Never apply automatically

### Additional System Rule

Cartero must remain usable across:

- CLI environments
- LLM-native environments (ChatGPT, Claude)

Both interfaces must maintain equivalent capabilities and remain aligned.

### Strategic Direction

Cartero evolves from:

- a system that generates communication from code changes

into:

- a system that continuously maintains alignment between code, context, and LLM workflows
---

## 10. Working Methodology

Every working session with Cartero follows this flow:

1. Start session with the current session brief. `cartero session` generates the session brief automatically from context/master-context.md. Run it at the start of each session and paste the output into your LLM conversation.
2. Implement the agreed feature or fix
3. Run all tests — no phase is marked complete until tests pass
4. Run `cartero commit` to generate the commit summary
5. The generated YAML is saved to `.cartero/yaml/` with a timestamp filename
6. Summarize what changed in the session
7. Update this master file before closing
8. Generate new session brief for next session

Before running `cartero commit`, create a context file summarizing the session decisions and tradeoffs. This step is currently manual — future improvement: make it explicit and guided in the commit flow so every commit includes full session context automatically.

This creates an observable history of how Cartero's LLM output quality improves with each phase.

### LLM Interaction Rules
- LLM outputs are Codex prompts by default. Code is only produced when explicitly requested
- Before generating any prompt, the LLM must state the plan and the facts it is pulling from context, and wait for confirmation if anything is uncertain

### Session Brief Format

The session brief is a lightweight document derived from this master file. It contains only what a fresh LLM needs to execute the next task without making decisions that contradict the architecture or roadmap.

Structure:
- **State** — last completed phase, what is pending validation
- **Strategic Direction** — fixed in every brief, never changes
- **Task** — next phase with enough detail to execute
- **Modules involved** — only modules touched by this task
- **Rules (non-negotiable)** — only rules an LLM would violate by default
- **End of session** — reminder to summarize, update master, generate new brief

### Timestamp Rule
The timestamp at the top of this document must be updated on every edit.
The user provides the timestamp — LLMs must never invent it.

### `cartero session` (future command — Phase X.7)
`cartero session` generates the session brief automatically from context/master-context.md. Run it at the start of each session and paste the output into your LLM conversation.

---

## 11. Detailed Reference

### CLI

cartero run <summary.yaml>  
cartero run --dry-run <summary.yaml>  
cartero run --apply <summary.yaml>  
cartero generate  
cartero generate --diff-file <path>  
cartero generate --context-file <path>  
cartero generate --stdin  
cartero commit  
cartero commit --context-file <path>  
cartero context  
cartero session  

---

### Output File Structure

.cartero/
- yaml/
- changelog/
- faq/
- marketing/

Files are named using date + UUID and never overwrite each other.

---

### Module Map

- cartero/llm.py — LLM calls, retry, chunking, delimiter-based structured plain-text output, in-memory regex parsing, system-controlled final formatting, multi-provider routing  
- cartero/generator.py — generation API, context integration  
- cartero/config.py — configuration  
- cartero/cli.py — CLI entrypoint  
- cartero/web.py — Flask API  
- cartero/validator.py — YAML validation  
- cartero/executor.py — apply changes  
- cartero/simulator.py — dry-run  
- cartero/git.py — git operations  

---

### Config

- model: claude-haiku-4-5-20251001  
- max_tokens: 8192  
- max_retries: 3  
- max_diff_tokens: 30,000  
- clean_after_publish_days: 7  

---

### Test Coverage

48 tests passing:

- LLM generation (chunking, retry, validation)
- CLI behavior
- Web endpoints
- Commit flow

---

## 12. Update Guidelines (for LLMs / Codex)

### Rules
- Do not rewrite entire sections unnecessarily
- Preserve structure and tone
- Reflect only implemented features (not speculative)
- Keep roadmap complete (do not remove phases)
- Clean redundancy but do not remove information
- Mark changed text with [square brackets] describing what changed
- Remove square brackets from previously marked changes (they become permanent)
- Update the timestamp at the top on every edit — always ask the user for the current time, never invent it

### Always follow Working Methodology
- Every session ends with `cartero commit`
- The `.cartero/yaml/` timestamp file is committed with the code
- This document is updated and timestamped before closing the session

### Update Triggers
Update this file when:
- a feature is completed
- a new feature begins
- priorities change
- architecture changes
- a product insight is validated

### Reminder Rule
If significant work has been completed and this file is not updated, remind the user to update it before continuing.
<!-- Last updated: 2026-04-04 18:45 — Session: wizard Step 3 real generation connected and validated, Phase 5.1 complete -->
