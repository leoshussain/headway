# Headway

Headway is an experimental public-transit reliability engine in development.

Published schedules and realtime countdowns can say that a bus is ten minutes
away, but that prediction is not the same as a dependable journey. A bus may
arrive early, late, in a bunch, or not when a rider can reasonably expect it at
all. Headway is an attempt to measure that gap: how long transit journeys
actually take, how consistently service arrives, and how observed service
differs from the schedule.

The engine is intended to remain provider-agnostic. Development currently uses
Societe de transport de Montreal (STM) data, and the only implemented flow is a
collector that archives STM GTFS-Realtime feeds for later analysis.

## Current state

Headway currently:

- polls STM trip updates and vehicle positions concurrently;
- validates each response by decoding its GTFS-Realtime protobuf message;
- stores the original response bytes as timestamped `.pb` snapshots;
- loads typed settings from the environment, `.env`, and packaged YAML defaults;
- runs locally with Python and `uv`, or in Docker.

Static GTFS loading, routing, normalized historical storage, reliability
metrics, an API, and a user interface are planned, not implemented.
## Quick start

The Docker workflow is recommended for a consistent Python and dependency
environment. It is also the environment used by the repository's dev-container
configuration.

Requirements:

- Docker Desktop or Docker Engine with Compose
- an STM API key

Create your local environment file from the safe template:

```console
cp .env.example .env
```

Replace the placeholder in `.env` with your key. Then build and start the idle
development container:

```console
docker compose build app
docker compose up -d app
docker compose exec app python -c "from headway.realtime.models import FeedInfo; print(FeedInfo)"
```

This does **not** start collection. See [DOCKER.md](DOCKER.md) for an explanation
of the Docker setup, dev containers, testing, and common development tasks.

### Native Python alternative

Headway requires Python 3.13 and [`uv`](https://docs.astral.sh/uv/):

```console
uv sync --frozen --all-groups
cp .env.example .env
uv run pytest
```

Replace the placeholder in `.env` before running the collector. `pytest`
currently reports that no tests were collected because the initial test suite
has not been written yet.

## Collect realtime data

The collector makes live requests to STM every 30 seconds and runs indefinitely.
It has no command-line options, so even `headway-collect --help` starts polling.
Start it only when you intend to collect data, and stop it with `Ctrl+C`:

```console
uv run headway-collect
```

With Docker, collection is a separate opt-in service:

```console
docker compose up -d collector
docker compose logs -f collector
docker compose stop collector
```

Pressing `Ctrl+C` while following logs stops the log view, not the collector.

## Configuration

`PROVIDERS__STM__API_KEY` is the only required local setting. The double
underscore expresses nested configuration: provider `stm`, field `api_key`.
Never commit `.env` or paste credentials into logs, issues, or documentation.

The packaged defaults configure two STM feeds with 30-second polling intervals
and use `data/` as the storage root. Settings provided directly in code take
precedence over environment variables, followed by `.env`, packaged defaults,
and file secrets.

Snapshots are written to:

```text
data/realtime/raw/stm/
|-- stm_trip_updates/<feed-header-timestamp>.pb
`-- stm_vehicle_positions/<feed-header-timestamp>.pb
```

These are untouched provider payloads. The timestamp comes from the GTFS-RT
header, and a repeated timestamp overwrites the existing file. The `data/`
directory is ignored by Git, but it grows continuously while collection runs;
storage retention and compaction are not implemented yet.

## Development checks

Run the project checks natively with:

```console
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check
```

Or run the same tools in the development container:

```console
docker compose exec app uv run pytest
docker compose exec app uv run ruff check .
docker compose exec app uv run ruff format --check .
docker compose exec app uv run pyrefly check
```

## Architecture

The implemented path is deliberately small:

```text
STM GTFS-RT feeds
        |
        v
RealtimeCollector -- decodes and validates the response
        |
        v
FileSink -- stores the original bytes under data/realtime/raw/
```

`RealtimeConfig` resolves provider, feed, interval, and storage settings. The
application entrypoint creates one shared HTTP client and polls the two current
STM feeds concurrently. The `headway.gtfs` package is only a placeholder today.

As the project grows, transit-domain and reliability logic should remain
independent of provider endpoints, HTTP clients, file formats, Docker, APIs, and
visualization concerns.

## Where this is going

The next major stages are static GTFS ingestion, scheduled routing, normalized
historical storage, and the first reliability analyses.
