# Cartero LLM Project Instructions

## Product Identity

Cartero is a system that turns code changes into structured, reusable communication across multiple outputs, including commit summaries, changelogs, FAQs, knowledge bases, and product updates.

It evolves from a YAML validation tool into an AI-assisted change orchestration and documentation system for vibe coders and non-technical users.

Cartero is not a commit generator. It is a communication system.

Core model:
- diff explains what changed
- context explains why it matters
- combining both produces significantly higher-quality outputs

## Source Model

- `git diff` is required and is the source of truth for what changed
- context is optional and provides intent for why it matters
- context improves output quality but never overrides the diff

## Hard Rules

### Output Rules
- LLM returns structured plain-text using custom delimiter markers
- the system parses model output into internal structured data
- the system controls final output formatting
- never invent actions or changes not present in diff or context
- never include lock files, generated files, or file content exceeding 500 characters

### Tone Rules
- write for both humans and LLMs
- use product release note style similar to Notion or Linear
- every summary must start with `Cartero`
- do not use git verbs: `fix`, `refactor`, `chore`, `update`, `patch`

### System Rules
- diff remains the source of truth
- context provides intent
- context is optional but improves output quality

### Architecture Rules
- maintain parity between CLI and web for all features
- keep Cartero usable across CLI environments and LLM-native environments such as ChatGPT and Claude

## Current Implemented Capabilities

- Validate YAML summaries
- Simulate execution with `--dry-run`
- Apply changes with `--apply`
- Generate summaries from git diffs with `cartero generate`
- Detect git diffs automatically without stdin
- Accept optional context via `--context-file`
- Compress raw context into a structured recap with `cartero context`
- Stage files and generate commits with `cartero commit`
- Support interactive file selection for commits
- Produce plain-language PMM-style summaries
- Retry LLM calls with stricter prompt on failure
- Split large diffs into per-file chunks
- Merge chunked outputs
- Propagate warnings to CLI and web
- Support multiple LLM providers: Anthropic and Gemini

## Current Priorities

1. Documentation Package (Phase 5)
2. GitHub Integration (Phase 6)
3. Guided CLI Flow (Phase 6.5)
4. UX / Flow Simplification
5. Repository & Presentation Layer
6. File Management (Deprioritized)

## Behavior Expectations

- treat `context/master-context.md` as the source of truth for project state
- reflect only implemented capabilities as implemented
- keep roadmap work separate from current capabilities
- preserve priorities exactly as defined in the master context
- preserve Cartero product identity and communication-system framing
- if context is provided, compress it into a recap with:
  - goal
  - user problem
  - decisions
  - tradeoffs
  - user impact
- follow the documented generation flow:
  1. process context if provided
  2. combine recap and diff
  3. keep diff as source of truth
  4. generate structured plain-text output with custom markers
  5. parse fields in-memory using regex
  6. generate final output format
  7. validate output

## Architecture

- receive diff
- optional context
- context to recap
- split into chunks if needed
- call the LLM per chunk
- merge results
- generate structured plain-text with custom markers
- parse fields in-memory with regex
- validate
- format final output

## Constraints

- output quality still needs improvement; summaries should be shorter and more product-like
- context input is still file-based and has friction
- full CLI workflow still requires multiple commands
- plain-text delimiter output replaced JSON output to eliminate parse instability across generation flows and pair well with streaming for the web UI

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

## Forbidden Behavior

- do not present roadmap work as completed functionality
- do not speculate beyond the master context
- do not override diff facts with context
- do not contradict current priorities
- do not break parity expectations across interfaces
