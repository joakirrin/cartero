# Cartero v0 YAML Contract

`cartero` v0 accepts a YAML file with exactly one top-level key: `actions`.

Schema:

```yaml
actions:
  - repo: <repo-name>
    type: <action-type>
    path: <relative-path>
    content: <optional-content>
```

Rules:

- `repo` must be one of `casadora-core`, `casadora-services`, `casadora-experiments`, `cartero`
- `type` must be one of `write`, `delete`, `mkdir`
- `path` must be a non-empty relative path using forward slashes
- `content` is required for `write`
- `content` is not allowed for `delete` or `mkdir`

CLI:

```bash
python -m cartero path/to/summary.yaml
```

The command validates the YAML, groups actions by repo, and prints a simulated dry-run plan. It does not modify files or git state in v0.
