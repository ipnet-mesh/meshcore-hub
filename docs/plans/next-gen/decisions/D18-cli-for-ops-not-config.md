# D18: CLI for Ops Only — One Config Surface Per Item

- **Status:** Locked
- **Iteration:** 5

## Context

Today the Click CLI mirrors config: `--retention-days` on the cleanup command, `--mqtt-host` as a service flag, and so on. This creates two problems. First, parameter explosion threads through `create_app` → `run_collector` — every CLI flag is another constructor argument that may or may not override the env var. Second, the "which wins, env or flag?" ambiguity is undocumented and inconsistent. The §5.1 principle 8 / §13-D18 question (iteration 5: user said "ditch CLI," then clarified "keep for migrations/management, just don't duplicate config"): shrink the CLI to genuine operational commands, or keep it as a third config surface?

## Decision

**CLI for ops only; one config surface per item.** A setting is either:

- a **Tier-1 env var** (bootstrap/infra — see D11), or
- a **Tier-2 DB/Admin-UI setting** (runtime),

**never also a CLI flag.** No `--retention-days` on the cleanup command when retention is a runtime setting; no `--mqtt-host` service flag when `MQTT_HOST` env var exists.

The Click group **stays** but shrinks to genuine operational commands that aren't config:

| Command | Purpose |
|---|---|
| `db upgrade` / `db revision` | Migrations (alembic) |
| `db export-config` / `db import-config` | Preserved-config migration (§18.2) |
| `admin create-user` | Headless bootstrap (D12) |
| `health` | Docker healthchecks |
| `cleanup --now` / `routes --rebuild` | Force-run a job outside its cadence |
| `settings reset --category=<cat>` | Escape hatch if a bad value bricks a service |

Runtime config lives in **env vars + the Admin UI exclusively.** `--now` / `--rebuild` are operational triggers ("run this job now"), not config overrides — the job reads its tuning from the Tier-2 settings.

## Consequences

**Positive:** Kills the "which wins, env or flag?" ambiguity entirely. Collapses the `create_app` → `run_collector` parameter threading. Operators have one place to change a setting (env for bootstrap, Admin UI for runtime) — no need to remember a CLI flag equivalent. CLI stays valuable for headless ops (CI-driven migrations, scripted bootstrap, Docker healthchecks).

**Negative:** Operators who today tune via CLI flags must move to the Admin UI (or env for Tier-1) — a workflow change. The `settings reset` escape hatch is CLI-only, which is a minor inconsistency (justified: it is the recovery path when the UI is broken).

## Alternatives considered

| Option | Verdict |
|---|---|
| **CLI for ops only; one config surface per item** (chosen) | Eliminates config duplication; CLI stays for genuine ops commands. |
| Drop the CLI entirely | Rejected — loses headless ops (CI migrations, scripted bootstrap, Docker healthchecks). |
| Keep CLI as today (full config-mirroring flags) | Rejected — preserves the parameter-explosion and "which wins?" ambiguity. |
| CLI as the *primary* config surface (env deprecated) | Rejected — config belongs in env (bootstrap) or DB (runtime) for auditability and restart-free changes; CLI is interactive-only. |
