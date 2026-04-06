<<<CARTERO_SESSION_V1>>>
goal: improve session-context ingestion in Cartero
user_problem: commit quality depends on context that is currently too manual to capture
decisions: add cartero session as the import/status entrypoint / persist raw and normalized artifacts for comparison
tradeoffs: use a strict parser first to keep debugging simple / leave commit flow unchanged in phase 1
user_impact: developers can reuse structured session context with less manual setup
risks_open_issues: the parser may reject slightly malformed blocks / command naming may still be confusing with the existing session brief flow
<<<END_CARTERO_SESSION_V1>>>