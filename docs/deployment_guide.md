# Deployment Guide — AWS MVP Instance

This guide details the steps to deploy an Orchestra MVP automation instance on AWS. The deployment uses a single EC2 instance running the Docker Compose stack over HTTP.

This is the simplest way to test run the stack on AWS.


## What You Need

- An **AWS account**.
- An **LLM API key** (OpenAI, Anthropic, or Gemini) and any other relevant creds for the playbooks.

<br>

## Deployment Steps


### 1. Launch the EC2 Instance
Create a virtual machine in the AWS Console:
- **AMI**: Ubuntu Server 26.04 LTS.
- **Instance Type**: `t3.small`.
- **Create/Add SSH key pair**
- **Storage**: 20 GB gp3.
- **Security Group**:
  - Allow **SSH (Port 22)** from your IP.
  - Allow **HTTP (Port 80)** from anywhere (for incoming webhooks).

### 2. Install Docker on the VM
SSH into the instance using your private key (`-i` flag is required):
```bash
ssh -i /path/to/your-key.pem ubuntu@<EC2-PUBLIC-IP>
```
Once connected, install Docker and its compose plugin:
```bash
sudo apt-get update
sudo apt-get install -y python3-pip docker.io docker-compose-v2
sudo usermod -aG docker ubuntu
```
> **Note: Log out and log back in to apply the docker group changes.**

### 3. Clone, Install, and Build the Framework
On the EC2 VM, clone the framework, install the `orchestra` CLI, and build the Docker image:
```bash
git clone https://github.com/orchestra-admin/orchestra.git
cd orchestra

# Install the orchestra CLI onto your PATH
sudo pip install -e . --break-system-packages 

# Build the Docker image used by the docker-compose stack
docker build -t orchestra/orchestra:latest .
```

### 4. Scaffold the Workspace
Create a separate workspace directory and run `orchestra init` to scaffold it:
```bash
mkdir -p ~/orchestra_workspace && cd ~/orchestra_workspace
orchestra init
```

`orchestra init` copies all template assets (playbooks, musicsheets, `docker-compose.yml`, `nginx.conf`, `.local_config/`) into the current directory and generates a `.env` file with a random `WEBHOOK_SECRET` pre-filled.


### 5. Configure Secrets

On the EC2 instance, open `~/orchestra_workspace/.env` to fill in your API keys:
```bash
vim ~/orchestra_workspace/.env
```
Add your credentials:
```env
OPENAI_API_KEY=sk-...
VT_API_KEY=...
SLACK_WEBHOOK_URL=...
```

> `WEBHOOK_SECRET` is already set — `orchestra init` generates it automatically. Do not change it unless you want to rotate the secret.

<br>

## Start and Verify the Stack

Run the stack in detached mode:
```bash
cd ~/orchestra_workspace
docker compose up -d
```

### Verification Steps

1. **Verify Health Endpoint**:
   ```bash
   curl http://<EC2-PUBLIC-IP>/health
   # Expected: {"status":"healthy"}
   ```

2. **Send a Test Webhook**:
   ```bash
   WEBHOOK_SECRET="<the-value-from-.env>"
   PAYLOAD='{"event_type":"ip_enrichment","ip":"8.8.8.8"}'
   SIG=$(printf '%s' "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" -hex | awk '{print $2}')

   curl -i -X POST http://<EC2-PUBLIC-IP>/webhook \
     -H "Content-Type: application/json" \
     -H "X-Orchestra-Signature-256: sha256=$SIG" \
     -d "$PAYLOAD"
   # Expected: HTTP 200 + {"queued":true,"job_id":"...","event_type":"ip_enrichment"}
   ```

3. **Check Orchestra Logs**:
   ```bash
   # cd to your workspace
   cat logs/orchestra.log
   ```

<br>


### Troubleshooting

- **`/health` returns connection refused**: The nginx container is not up. Check Nginx logs: `docker compose logs nginx`.
- **Webhook returns 401 Unauthorized**: The signature generated in your test command does not match the `WEBHOOK_SECRET` configured in `.env`. Verify the secret and restart the stack: `docker compose restart`.
- **Musician logs show connection errors**: The Redis container is not running or unreachable. Restart Redis: `docker compose up -d redis`.

<br>

### Next Steps

For production scale-out:
- **TLS termination**: Configure HTTPS using ACM and an Application Load Balancer (ALB).
- **AWS SSM Parameter Store**: Set `secrets.backend` in `.local_config/orchestra.json` to `"aws_ssm"` to avoid exposing credentials in a `.env` file.
- **ECS Fargate**: Move the Docker Compose services into managed Fargate tasks.
