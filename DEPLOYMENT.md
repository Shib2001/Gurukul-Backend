# Beginner deployment guide (Docker)

This project can run as three containers: the FastAPI backend, PostgreSQL, and
Redis. In production, an optional Caddy container provides HTTPS. PostgreSQL and
Redis are not published to the internet; database files persist in a Docker
volume.

## Railway deployment (managed platform)

Railway can build the backend from this repository's `Dockerfile` and run
PostgreSQL as a separate managed service. Use this route if you do not want to
maintain a VPS. Railway pricing and trial/free allowances can change; confirm
current costs and database persistence limits in your Railway account.

1. Push the code to GitHub. Make sure `.env` is not in the commit. If its
   credentials were ever pushed, rotate them.
2. In Railway, create a project and choose **Deploy from GitHub repo**. Select
   this repository and the `main` branch. Railway should detect the root
   `Dockerfile`; leave the root directory as `.`.
3. In the project, add a PostgreSQL service. Do not expose its public URL to the
   backend. In the backend service's Variables, add `DATABASE_URL` using Railway's
   reference-variable picker to refer to the PostgreSQL service's `DATABASE_URL`.
   The backend converts Railway's `postgresql://` URL to the async SQLAlchemy
   driver it uses.
4. Add backend Variables:

   ```text
   APP_ENV=production
   SESSION_SECRET=<generate a unique random value>
   FRONTEND_ORIGINS=https://your-frontend-domain.example
   EMAIL_VERIFICATION_RETURN_CODE_IN_RESPONSE=false
   PASSWORD_RESET_RETURN_CODE_IN_RESPONSE=false
   ```

   Generate a secret locally in PowerShell with
   `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   Enter the output into Railway's variable editor; do not commit it. Add SMTP
   variables there too if you want account verification and password-reset
   emails to work.
5. Deploy the backend. The Docker startup command applies Alembic migrations
   before launching the API and listens on Railway's assigned `PORT`.
6. In the backend service's Networking settings, generate a public domain. Set
   a health-check path of `/health/live` if Railway offers that setting. Check
   the deploy logs, then visit `https://<generated-domain>/docs`.

The current auth API does not require Redis, so do not add a Redis service just
for this deployment. The local Docker Compose setup is separate; Railway uses
the Dockerfile and its managed PostgreSQL service.

## 1. Prepare a server

Rent a small Ubuntu VPS from a hosting provider and point a domain or subdomain
(for example, `api.example.com`) to the server's public IP with a DNS A record.
Install Docker Engine and the Docker Compose plugin on that server using
Docker's official Ubuntu installation guide:
<https://docs.docker.com/engine/install/ubuntu/>.

Allow inbound TCP ports 80 and 443 in the hosting provider's firewall. SSH
(usually port 22) should be restricted to your own IP when possible.

## 2. Get the code onto the server

SSH into the server and run:

```bash
git clone <your-backend-repository-url> Gurukul-Be
cd Gurukul-Be
cp .env.example .env
```

Edit `.env` on the server. Set at least:

```dotenv
APP_ENV=production
POSTGRES_DB=gurukul
POSTGRES_USER=gurukul
POSTGRES_PASSWORD=<a-long-random-URL-safe-value>
DOMAIN=api.example.com
SESSION_SECRET=<a-random-secret-at-least-32-characters>
FRONTEND_ORIGINS=https://your-frontend-domain.example
```

Generate random values without showing or sending them anywhere:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Run it once for `POSTGRES_PASSWORD` and again for `SESSION_SECRET`. Keep the
values private. A URL-safe password avoids special-character issues in the
database connection URL built by Compose.

Fill in your SMTP settings if registration and password-reset emails should
work. Keep both `EMAIL_VERIFICATION_RETURN_CODE_IN_RESPONSE` and
`PASSWORD_RESET_RETURN_CODE_IN_RESPONSE` set to `false` in production.

## 3. Start the deployment

From the repository folder on the server:

```bash
docker compose --profile production up --build -d
```

The first start builds the backend Docker image on the EC2 server from the
repository's `Dockerfile`, starts PostgreSQL and Redis, waits for their health
checks, applies Alembic migrations, and then starts the API. Caddy requests and
renews the HTTPS certificate for `DOMAIN` automatically. Once the containers
are healthy, visit `https://api.example.com/docs` and
`https://api.example.com/Prod-test-prep` (replace this with your domain). To
confirm the built image is present on the server, run `docker image ls`.

Useful commands:

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f caddy
docker compose down
```

`docker compose down` stops and removes the containers but leaves the named
database and Caddy volumes intact. **Do not run `docker compose down --volumes`
unless you intentionally want to delete that persistent data.**

## 4. Deploy a later code update

After pushing code changes to the repository:

```bash
git pull
docker compose --profile production up --build -d
```

The backend runs `alembic upgrade head` before starting. Back up PostgreSQL
regularly and test restoring a backup; a Docker volume is persistent storage,
not a backup.

## Local Docker test

On a computer with Docker Desktop, copy `.env.example` to `.env`, set a
URL-safe `POSTGRES_PASSWORD` and a `SESSION_SECRET`, and run:

```powershell
docker compose up --build -d
```

Open <http://localhost:8000/docs>. This local command does not start Caddy. To
stop the containers while preserving the database:

```powershell
docker compose down
```

The `.env` file contains secrets and is ignored by Git. Commit `.env.example`,
never `.env`.
