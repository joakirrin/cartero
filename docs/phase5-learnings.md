# Phase 5 Learnings

## What Worked

- Diff + structured context produces high-quality summaries
- Extreme case testing revealed important guardrails
- Separating commits improves Cartero output quality

## Issues Found

- CLI entrypoint bug caused silent failures
- Cartero mixes communication with execution actions in some outputs
- Environment setup (API keys) can introduce confusion

## Key Insight

Cartero must:
- strictly separate communication from execution
- remain conservative when diff is ambiguous
- rely on context without overriding diff

## Next Focus

- Fix packaging / uv run issue
- Improve output format (reduce action noise)
- Compare Cartero outputs vs GitHub commits
