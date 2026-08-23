# Developing Headway with Docker

This guide assumes no previous Docker experience. It explains both the commands
to run and what Docker is doing with the project.

## The four pieces

- A **Dockerfile** is a recipe. Headway's recipe starts with Python 3.13 and
  `uv`, installs the locked dependencies, copies the package source, and installs
  the package.
- An **image** is the read-only environment produced from that recipe. Rebuilding
  creates an updated image; it does not edit your source files.
- A **container** is a running process created from an image. Containers can be
  stopped and replaced without losing files stored on your computer.
- **Docker Compose** reads `compose.yaml` and gives the project's containers
  stable names and settings. Headway defines an idle `app` service for
  development and an opt-in `collector` service for live collection.

The project directory is bind-mounted at `/app` inside each container. A bind
mount means the container sees files from your computer rather than a separate
copy: an edit in PyCharm is immediately visible at `/app`.

The development service can write to the project because development tools need
to update files. The collector sees the project as read-only, with one writable
exception for `/app/data`. This limits an unattended collector to writing its
snapshots instead of changing source or configuration.

## Install Docker

On Windows, install Docker Desktop and enable its WSL 2 backend. Docker Desktop
must be running before Docker commands will work. Open a new terminal and check:

```console
docker --version
docker compose version
```

On Linux, install Docker Engine and the Compose plugin using the instructions
for your distribution.

## Prepare credentials

The current collector needs an STM API key. From the project root, copy the
committed template:

```console
cp .env.example .env
```

On PowerShell, `Copy-Item .env.example .env` is the equivalent command. Replace
`your-stm-api-key` in `.env` with the real value.

`.env` is ignored by both Git and the Docker image build. It remains on your
computer and becomes visible at runtime through the project bind mount. Do not
commit it, include its contents in bug reports, or put a key directly in
`compose.yaml` or the Dockerfile. If a key is exposed, revoke or rotate it.

## Build the image

Run this from the project root:

```console
docker compose build app
```

The first build downloads the base image and installs the exact dependencies in
`uv.lock`. Docker caches each completed Dockerfile step, so later builds are
usually faster. Changes to `pyproject.toml` or `uv.lock` invalidate the dependency
layers and require installation to run again.

The image's virtual environment is `/opt/venv`, outside `/app`. This matters on
Windows: mounting the project at `/app` cannot replace the container's Linux
environment with the host's incompatible `.venv` directory.

## Start development

Start only the idle development service:

```console
docker compose up -d app
```

- `up` creates and starts the service.
- `-d` means detached, so it keeps running after the terminal returns.
- `app` selects only the development service.

The collector is assigned to an opt-in Compose profile. As an additional safety
measure, plain `docker compose up -d` also starts only `app`; it cannot
accidentally begin live collection.

Check that the installed package can be imported:

```console
docker compose exec app python -c "from headway.realtime.models import FeedInfo; print(FeedInfo)"
```

`exec app` runs the following command inside the already-running development
container. You can also open an interactive Python prompt:

```console
docker compose exec app python
```

## Dev containers

The `.devcontainer/devcontainer.json` configuration asks a compatible IDE to
use the `app` service as the development environment. Opening the repository in
the dev container therefore gives the IDE the container's Python interpreter,
terminal, and dependencies while the source remains on your computer.

On first creation, the configuration runs `uv sync --frozen --all-groups` and
installs its development tools. Starting the dev container does not start the
collector because `runServices` contains only `app`.

The dev-container configuration also keeps OpenCode and JetBrains backend state
in named Docker volumes. Rebuilding the container therefore preserves the
OpenCode installation state, JetBrains AI plugin, and JetBrains authentication.
Removing those named volumes explicitly will reset that state.

The container declares `/opt/venv/bin/python` as PyCharm's interpreter through
`PYCHARM_PYTHON_PATH`. The checked-in project metadata deliberately does not name
a host interpreter: a Windows `.venv` path would be invalid inside the Linux
container, while another contributor's local path would be invalid on your
machine.

After changing this setting, close the remote-development session and use
**Rebuild Container** before reconnecting. If an older PyCharm backend still
shows **No interpreter**, open **Settings | Python | Interpreter**, add an
existing local interpreter, and select `/opt/venv/bin/python` inside the
container. Some older PyCharm remote-development builds do not automatically
assign `PYCHARM_PYTHON_PATH`, even though the interpreter is present.

Rebuilding a dev container is not the same as rebuilding the Docker image:

- rebuild the image after Dockerfile or dependency changes;
- rebuild/reopen the dev container when its own configuration or features
  change;
- make ordinary source edits without rebuilding either one.

## Run project checks

With `app` running:

```console
docker compose exec app uv run pytest
docker compose exec app uv run ruff check .
docker compose exec app uv run ruff format --check .
docker compose exec app uv run pyrefly check
```

## Run the realtime collector

This is an intentional live operation. It contacts STM, writes protobuf files
approximately every 30 seconds for each configured feed, and runs indefinitely.

Start only the collector:

```console
docker compose up -d collector
```

Naming `collector` explicitly activates its opt-in profile. It does not start
the `app` service. Follow its logs with:

```console
docker compose logs -f collector
```

Pressing `Ctrl+C` stops following the logs but leaves the detached collector
running. Check its state and stop it explicitly with:

```console
docker compose ps
docker compose stop collector
```

The collector uses `restart: unless-stopped`, so Docker restarts it after a
failure or Docker Desktop restart until you explicitly stop it. Its Docker logs
rotate after three 10 MB files, but collected data has no automatic retention.
At the default intervals, two feeds can create as many as 5,760 files per day.
Monitor and clean `data/` deliberately.

## Everyday workflows

### Source-only change

The bind mount makes edits immediately visible in `app`; no image rebuild is
needed. A running Python process does not reload itself, so restart the collector
after changing collector source:

```console
docker compose restart collector
```

### Dependency change

Update `pyproject.toml`, refresh the lock file, rebuild, and replace any running
containers so they use the new image:

```console
uv lock
docker compose build
docker compose up -d --force-recreate app
docker compose up -d --force-recreate collector
```

Run the final collector command only if collection was already intended. If
`uv` is not installed on the host, run `docker compose exec app uv lock` instead.

### Dockerfile change

Rebuild and replace the affected running services:

```console
docker compose build
docker compose up -d --force-recreate app
```

Recreate `collector` separately if it is in use.

### Dev-container configuration change

Use the IDE's **Rebuild Container** action. Changes under `.devcontainer/` are
interpreted by the IDE rather than by a running Python process.

## Stop and clean up

Stop and remove this project's containers and Compose network:

```console
docker compose down
```

This does not delete source, `.env`, collected data, or built images. To rebuild
from scratch without Docker's layer cache, use `docker compose build --no-cache`.
That is rarely necessary.

## Troubleshooting

Show service state and recent logs:

```console
docker compose ps
docker compose logs app
docker compose logs collector
```

Render and validate the Compose configuration:

```console
docker compose config
```

Common causes of failure:

- `docker: command not found`: Docker is not installed or the terminal needs to
  be reopened after installation.
- Cannot connect to the Docker daemon: Docker Desktop or Docker Engine is not
  running.
- Collector configuration error: `.env` is missing, the placeholder was not
  replaced, or the variable is not named `PROVIDERS__STM__API_KEY`.
- Source changes do not affect collection: restart the long-running collector
  process with `docker compose restart collector`.
- Dependency imports fail after editing `pyproject.toml`: update `uv.lock`, then
  rebuild and recreate the container.

## Repository files

- `Dockerfile` defines the shared Python environment.
- `compose.yaml` defines the development and collection processes.
- `.devcontainer/devcontainer.json` connects a compatible IDE to `app`.
- `.dockerignore` excludes local environments, Git metadata, notebooks, tests,
  documentation, and data from the image build context.
- `.env.example` documents required secret names without containing secrets.
- `uv.lock` pins Python dependency versions.

`.dockerignore` affects only files sent to `docker compose build`. It does not
hide those files from a running container when the project directory is bind-
mounted. Runtime access is controlled separately by the mounts in `compose.yaml`.
