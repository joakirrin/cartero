# Cartero Context Validation Checklist

## Source Integrity

- `context/master-context.md` was read before derived files were generated
- derived files were generated from the master context, not from memory
- no derived file was created before the master context was current

## Product Identity

- Cartero is described as a communication system
- the diff-versus-context model is preserved
- context is optional and improves quality
- diff remains the source of truth

## Implemented Capability Validation

- only implemented capabilities are described as available
- current commands match the implemented capabilities
- current behavior includes context recap generation
- current behavior includes retry, chunking, merge, warnings, and multi-provider support

## Architecture Validation

- files reflect structured plain-text output with custom delimiter markers
- files reflect in-memory regex parsing
- files reflect system-controlled final formatting
- files do not present JSON output as the current architecture
- files do not present JSON-to-YAML conversion as the primary generation flow

## Priority Validation

- current priorities match the master context exactly
- no priority has been reordered, removed, or added

## Roadmap Validation

- roadmap content is preserved where referenced
- roadmap work is not presented as completed work
- speculative integrations are not described as current functionality
- GitHub integration remains a roadmap priority, not an implemented feature

## Constraint Validation

- no file invents actions or changes not present in diff or context
- no file allows context to override diff
- no file includes lock files, generated files, or file content exceeding 500 characters as output behavior

## Interface Parity Validation

- CLI parity with web is preserved
- Cartero is kept usable across CLI, web, and LLM-native environments

## Workflow Validation

- master context is updated before derived files are refreshed
- validation happens before approval
- `context/user-instructions.candidate.md` remains a candidate
- `context/user-instructions.md` remains the approved or live placeholder

## Prompt Validation

- files under `context/prompts/` are validated against the master context

## Approval Check

- all validation failures are resolved before approval
