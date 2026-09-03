# Self-hosting AMAlost

## Requirements

- Docker Desktop with Compose v2
- At least 8 GB RAM recommended for the CLIP/PyTorch backend
- A machine that stays awake while the service is public

## Start locally

```bash
cp .env.self-host.example .env
openssl rand -hex 32
```

Put the generated value in `.env` as `SECRET_KEY`, then replace the database password. Start the stack:

```bash
docker compose -f docker-compose.self-host.yml up --build -d
```

The frontend is available at `http://localhost:8080`. The first start runs Alembic migrations automatically. Check the result with:

```bash
docker compose -f docker-compose.self-host.yml logs -f api
```

The API is intentionally private to the Docker network. Test it through Nginx:

```bash
curl http://localhost:8080/api/
```

## Stop and update

```bash
docker compose -f docker-compose.self-host.yml down
git pull
docker compose -f docker-compose.self-host.yml up --build -d
```

Do not use `docker compose down -v` unless you intend to delete the database volume.

## Public access

For a public HTTPS deployment, point a domain or Cloudflare Tunnel at the frontend only: `http://localhost:8080`. Do not expose PostgreSQL (`5432`) or the API (`8000`) directly. Set `FRONTEND_BASE_URL` in `.env` to the public frontend URL before starting the stack.
