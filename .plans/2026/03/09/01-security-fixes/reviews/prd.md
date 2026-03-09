# PRD Review

> Phase: `.plans/2026/03/09/01-security-fixes`
> PRD: `.plans/2026/03/09/01-security-fixes/prd.md`
> Prompt: `.plans/2026/03/09/01-security-fixes/prompt.md`

## Verdict: PASS

The PRD fully covers all five security requirements from the prompt with clear, implementable, and testable acceptance criteria. No contradictions, blocking ambiguities, or feasibility concerns were found. One prompt goal ("Secure default MQTT configuration") has no corresponding requirement in either the prompt or the PRD, but since no prompt requirement addresses it, the PRD correctly does not fabricate one.

## Coverage Assessment

| Prompt Item | PRD Section | Covered? | Notes |
|---|---|---|---|
| C1+H2: Remove legacy HTML dashboard endpoint | REQ-001 | Yes | Route removal, import cleanup, sub-route preservation all specified |
| H1: Fix timing attack on API key comparison | REQ-002 | Yes | Files and `hmac.compare_digest()` approach match |
| H3: Harden admin auth / proxy header forgery | REQ-003 | Yes | Config setting, default, warning, Basic auth preservation all covered |
| H4: Fix XSS via config_json\|safe breakout | REQ-004 | Yes | Escape approach and XSS test payload specified |
| H5: Fix stored XSS via unsafeHTML/innerHTML | REQ-005 | Yes | Files, fix approach, and XSS test payloads specified |
| Constraint: No breaking changes to API contracts | REQ-006 | Yes | |
| Constraint: docker-compose.yml/mosquitto.conf backward-compatible | REQ-006 | Partial | REQ-006 covers Docker Compose but not mosquitto.conf; moot since no requirement changes mosquitto.conf |
| Constraint: _is_authenticated_proxy_request works with OAuth2 | REQ-003, REQ-007 | Yes | |
| Goal: Secure default MQTT configuration | -- | No | Goal stated in prompt but no prompt requirement addresses it; PRD correctly does not fabricate one |
| Out of scope items | Scope section | Yes | All exclusions match prompt |

**Coverage summary:** 5 of 5 prompt requirements fully covered, 1 constraint partially covered (moot), 1 prompt goal has no corresponding requirement in the prompt itself.

## Requirement Evaluation

All requirements passed evaluation. Minor observations noted below.

### REQ-003: Add configurable trusted proxy hosts

- **Implementability:** Pass -- A developer familiar with Pydantic Settings and `ProxyHeadersMiddleware` can implement this without ambiguity. The env var format (comma-separated list vs. single value) is not explicitly stated but follows standard Pydantic patterns.
- **Testability:** Pass
- **Completeness:** Pass
- **Consistency:** Pass

### REQ-006: Backward compatibility

- **Implementability:** Pass
- **Testability:** Pass
- **Completeness:** Pass -- The prompt constraint about mosquitto.conf backward compatibility is not explicitly mentioned, but no requirement modifies mosquitto.conf, making this moot.
- **Consistency:** Pass

## Structural Issues

### Contradictions

None found.

### Ambiguities

None that would block implementation. The `WEB_TRUSTED_PROXY_HOSTS` env var format is a minor detail resolvable by the developer from the `ProxyHeadersMiddleware` API and standard Pydantic Settings patterns.

### Missing Edge Cases

None significant. The `hmac.compare_digest()` change (REQ-002) assumes the existing code handles the "no key configured" case before reaching the comparison, which is standard practice and verifiable during implementation.

### Feasibility Concerns

None.

### Scope Inconsistencies

The prompt states a goal of "Secure default MQTT configuration against unauthenticated access" but provides no requirement for it. The PRD drops this goal without explanation. This is a prompt-level gap, not a PRD-level gap -- the PRD should not invent requirements that the prompt does not specify.

## Action Items

No action items. The PRD is ready for task breakdown.
