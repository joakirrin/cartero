# Cartero – Master Context

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
- Defined the Phase 5 canonical documentation contract for commit summaries, changelogs, FAQs, and knowledge base entries
- Defined the canonical record as the shared internal data model for documentation outputs
- Defined the transformation specification from diff + context into canonical Cartero records
- Defined the output/render layer for deterministic reuse of canonical records across output surfaces
- Defined the Codex prompt bridge structure for converting canonical records into agent-ready instructions
- Established a sequential prompting strategy: contract -> transformation -> output layer

---

## 4. Current Priorities (Active Now)

1. Documentation Package (Phase 5)  
2. GitHub Integration (Phase 6)  
3. Guided CLI Flow (Phase 6.5)  
4. UX / Flow Simplification  
5. Repository & Presentation Layer  
6. File Management (Deprioritized)

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

---

## 8. Open Decisions / Pending Validation

- Validation layer design:
  - how strictly to enforce canonical record compliance
  - where to stop malformed records in the pipeline

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

### Phase 5 — Documentation Package

- Improve output quality toward product-style communication (Notion / Linear level)
- Standardize output structure and formatting
- Ensure consistency across:
  - commit summaries
  - changelogs
  - FAQs
  - knowledge base entries
- Introduce reusable templates for different output types
- Replace JSON output with plain-text delimiter format — use structured plain-text with custom markers instead of JSON. Parse fields with regex in-memory. Eliminates parse failures across all generation flows and unblocks reliable output for GitHub integration, guided CLI, and web UI.

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

## 10. Detailed Reference

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

## 11. Update Guidelines (for LLMs / Codex)

### Rules
- Do not rewrite entire sections unnecessarily
- Preserve structure and tone
- Reflect only implemented features (not speculative)
- Keep roadmap complete (do not remove phases)
- Clean redundancy but do not remove information

### Update Triggers
Update this file when:
- a feature is completed
- a new feature begins
- priorities change
- architecture changes
- a product insight is validated

### Reminder Rule
If significant work has been completed and this file is not updated, remind the user to update it before continuing.
