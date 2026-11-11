# Deploy Gurukul Backend from another Windows laptop

This guide covers deploying to the **existing EC2 instance** from another
Windows laptop. It does not cover creating a new AWS instance or setting up
GitHub.

The temporary test deployment uses HTTP:

```text
http://<EC2-public-ip>:8000
```

HTTP is unencrypted. Use this only for testing; do not send real passwords or
sensitive data. If port 8000 is restricted to your IP, other users and services
will not be able to access the API.

## What you need on the other laptop

- PowerShell and the Windows OpenSSH client.
- The EC2 private key file, for example `gurukul-ec2.pem`, transferred securely.
  Never commit, email, or post this key. Anyone with the key and network access
  may be able to log in to the server.
- Access to the AWS account so you can view the instance and update its security
  group.
- The instance's current public IPv4 address.

You do **not** need Docker or AWS CLI on the laptop for this deployment process.
Docker runs on EC2; the laptop connects to it over SSH.

## 1. Find the instance and current public IP

1. Sign in to the [AWS Console](https://console.aws.amazon.com/).
2. Select the same AWS Region where the instance was created (the current
   instance is in Asia Pacific (Sydney), `ap-southeast-2`).
3. Open **EC2 > Instances** and select `gurukul-backend`.
4. Confirm the instance is **Running** and its status checks have passed.
5. Copy its current **Public IPv4 address**.

The public IP can change after the instance is stopped and started. Always check
the current address before connecting or testing the API.

## 2. Allow this laptop to connect

The new laptop will usually have a different public IP from the other laptop.
In **EC2 > Instances > gurukul-backend > Security**, open the attached security
group and edit its inbound rules:

- SSH: TCP port `22`, source **My IP**.
- Temporary API access: Custom TCP port `8000`, source **My IP**.
- Do not add public inbound rules for PostgreSQL (`5432`) or Redis (`6379`).

If you change Wi-Fi networks or use a VPN, your public IP may change; select
**My IP** again to update the SSH and API rules. Do not set SSH to Anywhere.

## 3. Connect from PowerShell

Open PowerShell on the new laptop. Update the key path and address if needed:

```powershell
$KeyPath = "$HOME\Downloads\gurukul-ec2.pem"
$PublicIp = "<current-EC2-public-ip>"
ssh -i $KeyPath "ec2-user@$PublicIp"
```

On the first connection, SSH may ask whether to trust the server host key. Type
`yes` only when you have initiated a connection to your EC2 instance.

When the prompt looks like this, commands are running on the EC2 Linux server:

```text
[ec2-user@ip-... ~]$
```

The `PS C:\...>` prompt means you are back on the Windows laptop.

If SSH times out, check the instance's current IP, ensure it is running, and
update the SSH security-group source to the new laptop's **My IP**. If SSH says
the key cannot be read, check `$KeyPath` points to the `.pem` file.

## 4. Deploy the application on EC2

Run these commands at the EC2 prompt, not at the Windows `PS` prompt:

```bash
cd ~/Gurukul-Backend
git pull --ff-only
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

`docker compose config --quiet` should finish without an error before the
deployment. The `up --build -d` command rebuilds the backend image, starts or
updates the containers, and runs the database migrations through the backend's
startup command.

### Preserve the server configuration and data

- Keep the EC2 server's `.env`. Do **not** replace it with `.env.example` or
  copy the other laptop's `.env` over it. The server file contains production
  settings and secrets.
- Do not print or share `.env` contents, database passwords, session secrets,
  or SSH private keys.
- PostgreSQL data is in the named Docker volume `postgres_data`. Do not run
  `docker compose down --volumes` or delete that volume; doing so deletes the
  database data.
- Changing `POSTGRES_PASSWORD` in `.env` does not change the password inside an
  already-initialized database. Rotate the database role password in PostgreSQL
  and update the server `.env` together.
- The EC2 Compose file must publish the backend on port `8000` for this
  temporary direct-HTTP test. Under `services.backend.ports`, it should contain:

  ```yaml
  - "${API_PORT:-8000}:8000"
  ```

  Keep PostgreSQL and Redis bound only to `127.0.0.1`, or without host port
  mappings. Do not publish their ports to the internet. This backend port
  binding is server-specific; if an update changes the Compose file, verify the
  mapping again before deploying.

## 5. Check the deployment

On EC2, inspect container status:

```bash
docker compose ps
```

Wait for PostgreSQL and Redis to show healthy and for the backend health status
to become healthy. If the backend is unhealthy or exits, inspect its logs:

```bash
docker compose logs --tail=100 backend
```

Do not paste logs publicly without checking that they contain no secrets.

From a browser on the laptop, test the current public address:

```text
http://<current-EC2-public-ip>:8000/health/live
http://<current-EC2-public-ip>:8000/test/root
http://<current-EC2-public-ip>:8000/docs
```

The health endpoint should return HTTP 200. If it times out, check that the
security group allows TCP `8000` from this laptop's current **My IP**, and that
the backend port is published as described above.

## 6. Stop or reconnect

Closing the SSH window disconnects the terminal but does not stop the
containers. To reconnect, run the SSH command in step 3 again.

To stop the application containers while leaving the EC2 instance and database
volume in place, run this on EC2:

```bash
cd ~/Gurukul-Backend
docker compose down
```

To start them again:

```bash
cd ~/Gurukul-Backend
docker compose up -d
```

Do not use `docker compose down --volumes` unless you intentionally want to
delete the database data.

## Temporary OTP setting

The API can return email-verification codes only when
`APP_ENV=development` and `EMAIL_VERIFICATION_RETURN_CODE_IN_RESPONSE=true` are
set in the EC2 `.env`. This is for testing only: it exposes verification codes
in API responses. Keep port `8000` restricted to your IP and disable this
setting before real users use the service. For actual registration emails,
configure SMTP and use production settings.

## Switching to HTTPS later

The repository includes Caddy for HTTPS. When you have a hostname whose DNS
points to the EC2 instance, set `DOMAIN` in the EC2 `.env`, allow inbound ports
`80` and `443`, and start the production profile:

```bash
cd ~/Gurukul-Backend
docker compose --profile production up --build -d
```

Caddy can then obtain and renew a public TLS certificate for the hostname.
Keep the database and Redis ports private.
