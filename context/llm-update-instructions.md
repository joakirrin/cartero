# Cartero LLM Update Instructions

## Governing Rule

`context/master-context.md` is the source of truth for all derived context files.

No derived file may be created, refreshed, or approved from memory, inference, or roadmap interpretation alone.

## Required Update Workflow

1. Read `context/master-context.md`.
2. Extract current product identity, hard rules, implemented capabilities, current priorities, system behavior, architecture constraints, known issues, roadmap state, and approval boundaries.
3. Update derived files from the master context only.
4. Keep implemented capabilities separate from roadmap items.
5. Run validation across all derived files.
6. Require approval before any promotion step.

## Master-Context-First Rules

- Derived files must never be generated before the master context is current
- If significant work is complete and the master context is stale, refresh the master context first
- If a requested change is not grounded in the master context, do not add it
- If ambiguity exists, preserve the master context wording rather than expanding scope

## Allowed Behavior

- Rephrase the master context into operational instructions
- Reorganize information for clarity
- Separate implemented features from roadmap work
- Preserve the full roadmap without compressing it
- Preserve current priorities exactly
- Preserve Cartero product identity
- Preserve the diff-versus-context model
- Preserve the structured plain-text delimiter architecture
- Preserve parity requirements across CLI, web, and LLM-native environments

## Forbidden Behavior

- Invent functionality
- Mark speculative work as implemented
- Contradict the master context
- Compress or remove roadmap phases
- Change priorities
- Auto-promote user instructions
- Skip validation before approval
- Let context override the diff
- Break parity expectations between CLI usage and LLM-native environments such as ChatGPT and Claude

## Validation Rules

Validation must confirm:
- master context remains the source of truth
- implemented capabilities are reflected accurately
- roadmap content is preserved
- user instructions describe only current capabilities
- project instructions preserve hard rules and behavior expectations
- no file introduces speculative features as live functionality
- current priorities match exactly
- the structured plain-text delimiter architecture is reflected accurately

## Approval Rules

- Validation must happen before approval
- User instructions must never be auto-promoted
- Updates to the master context require human review
- Proposed updates to derived files may be reviewed after validation
- If validation fails, approval is blocked

## Update Standard

- clarity over verbosity
- structured over narrative
- precise over generic
- operational over descriptive
