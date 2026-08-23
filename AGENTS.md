# Headway Agent Notes

## Setup and checks

- Use Python 3.13 and `uv`; install the locked project plus all development groups with `uv sync --frozen --all-groups`.
- Run tests with `uv run pytest`; target one test with `uv run pytest tests/path/to/test_file.py::test_name`.
- Run lint, formatting, and type checks with `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pyrefly check`.
- Ruff and Pyrefly have no exclusions configured: full-repository checks inspect the prototype notebook, and Ruff also formats Python examples in Markdown. Use a changed-file scope for focused verification, but do not treat that as a replacement for reporting full-check failures.

## Current architecture

- The only implemented application flow is GTFS-Realtime collection under `src/headway/realtime/`; `src/headway/gtfs/` is currently only a package placeholder.
- `src/headway/realtime/__main__.py` is the composition root: it loads settings, creates one shared HTTP client and `FileSink`, then polls the two hard-coded STM feeds concurrently.
- `RealtimeCollector` owns fetch/decode/poll behavior; `FileSink` writes the untouched protobuf payload to `data/realtime/raw/<provider>/<feed>/<header_timestamp>.pb` by default.
- `docs/transit-reliability-project-summary.md` is a long-term roadmap, not a description of implemented modules. Preserve its important dependency direction: transit/domain logic must not depend on HTTP, storage formats, Docker, APIs, or provider-specific endpoints; avoid creating roadmap modules before they are needed.

## Collector configuration

- `RealtimeConfig` precedence is constructor values, environment, `.env`, packaged `resources/defaults.yaml`, then file secrets. Nested environment keys use `__`.
- Defaults define feeds and `data_dir: data` but deliberately define no provider credentials. Supply the required STM key as `PROVIDERS__STM__API_KEY`; never commit `.env`, credentials, or collected `data/`.
- `headway-collect` has no argument parser. `uv run headway-collect --help` still starts live, indefinite polling and writes data; run `uv run headway-collect` only when live collection is intended and stop it explicitly.
- The shared client's `apiKey` header comes from the first configured feed. Do not add a feed from another provider without changing client grouping/authentication.

## Docker workflow

- `docker compose up -d` starts the idle `app` development service; `docker compose up -d collector` starts the persistent collector.
- Source is bind-mounted, so source-only edits need no image rebuild, but the running collector must be reloaded with `docker compose restart collector`.
- After dependency changes, update `uv.lock`, then run `docker compose build` and recreate the service. The container environment lives at `/opt/venv` so the host `.venv` cannot shadow it.
