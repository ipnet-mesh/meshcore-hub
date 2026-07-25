# D15: PL/pgSQL Function for Spam Scoring (Online + Sweep)

- **Status:** Locked
- **Iteration:** 4

## Context

Today's spam scoring has two paths that share logic but not implementation: an **online** score computed at insert time (asymmetric — only looks at prior messages), and a **symmetric** rescore sweep that re-evaluates recent messages with hindsight (looks at prior + subsequent). Both are implemented in Python, with the sweep job issuing per-row queries against `messages` (`spam.py` ~315 LOC). The §13-D15 question: keep the Python implementation, move both paths into the database as a shared PL/pgSQL function, or split them across worker jobs?

## Decision

**One PL/pgSQL `STABLE` function `compute_spam_score(...)`**, shared by both call sites. Parameters: `p_msg_id`, `p_window` (interval), `p_min_path_hops`, `p_path_threshold`, `p_name_threshold`, `p_w_path` (float), `p_w_name` (float). The function computes the path-eligibility check, the windowed `path_prefix` + `sender_normalized` counts, and the weighted score — the same logic as today, expressed in SQL.

- **At insert** (IngestWorker): `UPDATE messages SET spam_score = compute_spam_score(id, ...) WHERE id = ?;`
- **Sweep** (`spam-rescore` job, 120s cadence): `UPDATE messages SET spam_score = compute_spam_score(id, ...) WHERE received_at > now() - '1 hour'::interval AND spam_score IS DISTINCT FROM compute_spam_score(id, ...);` — only writes changed rows.

## Consequences

**Positive:** One implementation shared by online + sweep — kills the asymmetric-online / symmetric-sweep Python split (`spam.py` ~315 LOC collapses to the function + two call sites). Pure function of its inputs → idempotent. The sweep's `IS DISTINCT FROM` check avoids unnecessary writes. Parameters are configurable via Tier-2 tuning settings (D11) — operators tune weights/thresholds at runtime.

**Negative:** PL/pgSQL is a less familiar language for contributors than Python; debugging requires DB-side tools. A bad parameter (e.g. enormous window) can make the function slow — mitigated by per-category Pydantic validation on the settings write. Schema changes to `messages` require updating the function.

## Alternatives considered

| Option | Verdict |
|---|---|
| **PL/pgSQL function** (chosen) | One shared implementation; collapses the Python split; idempotent. |
| Keep the Python implementation | Rejected — duplicated logic across online + sweep; per-row queries from Python are slower than in-DB computation. |
| Dedicated Python worker job for both paths | Rejected — still pulls rows to Python and writes back; PL/pgSQL avoids the round-trip. |
| Trigger-based (compute on INSERT via trigger) | Rejected — trigger adds hidden work on the hot write path; explicit call from the IngestWorker is auditable. |
