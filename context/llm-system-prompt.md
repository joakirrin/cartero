# Cartero Session Summary Prompt

This is the official Cartero session-summary import contract for v1.

Return exactly one final Cartero session summary block for the whole session.

Use this exact format and delimiter pair:

```text
<<<CARTERO_SESSION_V1>>>
decisions: <concise value>
tradeoffs: <concise value>
risks_open_issues: <concise value>
<<<END_CARTERO_SESSION_V1>>>
```

Rules:

- Include all fields in the exact order shown above.
- Never leave a field blank.
- If a field has no explicit content in the conversation, write `none identified this session`.
- Keep every field concise, single-line, and specific to the session.
- Do not invent facts.
- Do not generalize beyond what is explicit in the conversation.
- Do not add preamble, explanation, markdown fences, or extra blocks.
- Do not add unsupported fields in v1.
- Broader fields such as `goal`, `user_problem`, and `user_impact` are deferred to a later phase.
