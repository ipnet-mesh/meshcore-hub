# Tasks: Add sqlite3 CLI to Docker Image

> Generated from `plan.md` on 2026-05-17

## Dockerfile Update

- [x] Add `sqlite3` package to the runtime stage apt-get install
  - [x] Edit the `RUN apt-get install` block in the runtime stage
        (lines 86-90 of `Dockerfile`) to include `sqlite3` after `udev`
  - [x] Ensure `--no-install-recommends` and apt-list cleanup
        (`rm -rf /var/lib/apt/lists/*`) are preserved

## Verification

- [x] Rebuild the Docker image and confirm `sqlite3` is available
  - [x] Run `docker compose --profile core build` to rebuild
  - [x] Run `docker compose --profile core run --rm --entrypoint sqlite3
        api --version` to verify the binary is installed and executable
- [x] Run `pre-commit run --all-files` to confirm no lint issues
