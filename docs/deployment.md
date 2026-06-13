# Deployment Guide — MVP test instance

The guide aim to get an Orchestra MVP instance running on AWS. One EC2 instance, the shipped `docker-compose.yml`, HTTP only.

## What you need

- An **AWS account** and **AWS CLI v2** installed locally.
- An **SSH key pair** in the region you'll use.
- An **LLM API key** (OpenAI, Anthropic, or Gemini) — you'll paste it into `.env` later.
- An **initialized Orchestra project** on your workstation (see the main `README.md` Quick Start).

---

## 1. Build and push the image

From the framework repo root:

```bash
# Create the ECR repository once
aws ecr create-repository --repository-name orchestra --region <region>

# Authenticate Docker to ECR
aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com

# Build, tag, push
docker build -t orchestra:latest .
docker tag orchestra:latest <account>.dkr.ecr.<region>.amazonaws.com/orchestra:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/orchestra:latest
```

---

## 2. Launch one EC2 instance

In the AWS console:

- **AMI:** Ubuntu Server 22.04 LTS.
- **Instance type:** `t3.small` (or `t3.medium` if you expect >50 jobs/hour).
- **Storage:** 20 GB gp3.
- **Subnet:** a public subnet, with **Auto-assign public IP** enabled.
- **Security group:** allow **SSH (22)** from your IP, allow **HTTP (80)** from anywhere.
- **Elastic IP:** attach one so the address stays stable across reboots.

You can paste the following as **User data** to install Docker on first boot, or skip this and install it by hand after SSHing in:

```bash
#!/bin/bash
apt-get update
apt-get install -y docker.io
systemctl enable --now docker
usermod -aG docker ubuntu
```

---

## 3. SSH in and start the stack

```bash
ssh ubuntu@<elastic-ip>

# If you skipped the user data script:
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
# log out and back in so the docker group takes effect

# Authenticate to ECR and pull the image
aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker pull <account>.dkr.ecr.<region>.amazonaws.com/orchestra:latest

# Lay down the project on the VM
mkdir -p /opt/orchestra
cd /opt/orchestra
# From your workstation, scp the scaffolded project into this directory:
#   scp -r .env musicsheets playbooks nginx.conf docker-compose.yml .local_config \
#     ubuntu@<elastic-ip>:/opt/orchestra/

# Start everything
docker compose up -d
docker compose ps
```

---

## 4. Set your secrets

On the VM, open `.env` and put in at least one LLM key plus whatever the example playbook needs (VirusTotal, Slack). The shipped `docker-compose.yml` reads `.env` via the `env` secrets backend, so no IAM permissions are required for this MVP.

```bash
sudo $EDITOR /opt/orchestra/.env
docker compose restart
```

---

## 5. Verify

```bash
# Health endpoint
curl http://<elastic-ip>/health
# Expect: {"status":"healthy"}

# Send a real webhook (replace $WEBHOOK_SECRET with the value from .env)
WEBHOOK_SECRET="<the-value-from-.env>"

PAYLOAD='{"event_type":"ip_enrichment","ip":"1.1.1.1"}'
SIG=$(printf '%s' "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" -hex | awk '{print $2}')

curl -i -X POST http://<elastic-ip>/webhook \
  -H "Content-Type: application/json" \
  -H "X-Orchestra-Signature-256: sha256=$SIG" \
  -d "$PAYLOAD"
# Expect: HTTP 200 + {"queued":true,"job_id":"...","event_type":"ip_enrichment"}

# Tail the musician
docker compose logs -f musician
```

If `/health` returns 200 and a job shows up in the musician logs, the loop is closed.

---

## Troubleshooting

- **`/health` returns connection refused.** The nginx container is not up. Run `docker compose ps`; if `nginx` is restarting, check `docker compose logs nginx`.
- **Webhook returns 401.** The `WEBHOOK_SECRET` in `.env` on the VM doesn't match the secret used in the curl command. Re-paste, then `docker compose restart`.
- **Musician logs show `error.redis_connection`.** The redis container isn't running. `docker compose ps redis`; bring it back with `docker compose up -d redis`.

---

## Next steps

This MVP gets you to "a webhook landed and a musicsheet ran." The production hardening lives in separate, larger guides:

- **TLS** in front of the webhook (ACM + ALB or a reverse proxy): see [issue #34](https://github.com/orchestra-admin/orchestra/issues/34).
- **Secrets in SSM Parameter Store** instead of `.env` on disk: see `docs/deployment.md` once we publish the full guide, or the `secrets` block of `orchestra.json`.
- **ECS Fargate** with shared EFS for `musicsheets/` and ElastiCache for Redis: documented under the "Fargate" option of the full deployment guide.
- **Persistent job history** in SQLite/Postgres: see [issue #39](https://github.com/orchestra-admin/orchestra/issues/39).
