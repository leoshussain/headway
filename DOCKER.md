# Developing Headway with Docker

Docker packages the operating system tools, Python version, and Python
dependencies used by Headway into an **image**. A running instance of that image
is a **container**.

## 1. Install Docker

On Windows, install Docker Desktop and use its WSL 2 backend. After installation,
open a new terminal and verify it:

```powershell
docker --version
docker compose version
```

## 2. Build the image

From the project root, run:

```powershell
docker compose build
```

The first build downloads Python and installs the exact dependencies recorded in
`uv.lock`. Later builds reuse cached layers unless `pyproject.toml` or `uv.lock`
changes.

## 3. Start the development container

```powershell
docker compose up -d
```

Compose starts the `app` service in the background. The project directory is
mounted at `/app`, so edits made in PyCharm appear inside the running container
immediately.

Try importing the model that already exists:

```powershell
docker compose exec app python -c "from headway.realtime.models import RealTimeFeed; print(RealTimeFeed(url='https://example.com/feed', interval=30))"
```

Open a Python prompt inside the container:

```powershell
docker compose exec app python
```

Stop and remove the container when you are finished:

```powershell
docker compose down
```

This removes the container, not your source code or the built image.

## 4. Run the realtime collector

Start the collector in the background:

```powershell
docker compose up -d collector
```

The collector continues running after the terminal closes. It also restarts
automatically after a failure or a Docker restart unless you explicitly stop it.
Follow its logs with:

```powershell
docker compose logs -f collector
```

Press `Ctrl+C` to stop following the logs; this does not stop the collector.
Stop the collector itself with:

```powershell
docker compose stop collector
```

## Everyday rules

- Source-only edit: no rebuild is needed because the source is bind-mounted.
- Dependency edit: run `uv lock` locally, then `docker compose build` and
  `docker compose up -d` again.
- Dockerfile edit: rebuild the image.
- Collector source edit: restart it with `docker compose restart collector` so
  the running Python process loads the updated code.

## What each file does

- `Dockerfile` is the recipe for one reproducible Headway image.
- `compose.yaml` describes the development container and realtime collector.
- `.dockerignore` keeps local environments, Git history, notebooks, and data out
  of the image build context. These files still remain on your computer.
- `uv.lock` makes dependency installation reproducible.

The virtual environment lives at `/opt/venv` inside the image. Keeping it outside
`/app` prevents the project bind mount—and especially the Windows `.venv`
directory—from replacing the Linux environment in the container.
