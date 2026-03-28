# Cartero User Instructions Candidate

## What Cartero Does

Cartero turns code changes into structured communication outputs. Its current workflow includes validating structured outputs, generating summaries from git diffs, compressing optional context, and creating commits from selected changed files.

Cartero uses two inputs:
- `git diff` for what changed
- optional context for why it matters

The diff is always the source of truth.

## Current Commands

### Validate or run a summary

Use:

```bash
cartero run <summary.yaml>
cartero run --dry-run <summary.yaml>
cartero run --apply <summary.yaml>
```

What this does:
- validates structured summary files
- simulates execution with `--dry-run`
- applies changes with `--apply`

### Generate a summary from changes

Use:

```bash
cartero generate
cartero generate --diff-file <path>
cartero generate --stdin
cartero generate --context-file <path>
```

What this does:
- reads the current git diff automatically when no diff input is provided
- optionally reads context from a file
- generates a summary from the diff

### Compress context before generation

Use:

```bash
cartero context
cartero context --context-file <path>
```

What this does:
- compresses raw notes into a structured recap
- uses these recap fields:
  - goal
  - user problem
  - decisions
  - tradeoffs
  - user impact

### Stage files and create a commit

Use:

```bash
cartero commit
cartero commit --context-file <path>
```

What this does:
- shows changed files
- lets you select files interactively
- stages the selected files
- generates a summary from the staged diff
- creates a git commit after confirmation

## How Cartero Works

1. Provide a git diff directly or let Cartero detect it automatically.
2. Optionally provide context with `--context-file`.
3. Cartero compresses context into a recap.
4. Cartero combines recap and diff.
5. The diff remains the source of truth.
6. Cartero generates structured plain-text output with custom markers.
7. Cartero parses fields in-memory using regex.
8. Cartero generates the final output format.
9. Cartero validates the output.

## Outputs

Current outputs and behaviors:
- validated structured summary files
- dry-run execution previews
- applied changes from valid summaries
- generated commit summaries
- warnings surfaced in CLI and web

## Current System Behavior

- Cartero writes for both humans and LLMs
- summaries use a product release note style
- summaries must start with `Cartero`
- Cartero supports Anthropic and Gemini providers
- Cartero retries failed LLM calls with a stricter prompt
- Cartero splits large diffs by file and merges chunked results
- Cartero uses structured plain-text with custom delimiter markers, in-memory regex parsing, and system-controlled final formatting
- YAML validation remains available for `cartero run`, but YAML is not the core generation format

## Limitations

- context is optional but file-based today
- output quality still needs improvement; summaries should be shorter and more product-like
- full CLI workflow can require multiple commands
- Cartero must remain aligned across CLI, web, and LLM-native environments

## Boundaries

- Cartero does not invent changes that are not present in the diff or context
- context helps explain intent but does not override the diff
- lock files, generated files, and file content over 500 characters must not be included

This file is a candidate and must not be auto-promoted.
