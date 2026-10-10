# RCA Demo AWS setup and operation

This guide deploys the current simplified design: one Ubuntu EC2 instance runs
Docker Compose with Caddy and FastAPI. GitHub Actions tests changes, publishes
two public Docker Hub images, and sends their exact immutable digests to the
instance through a restricted Systems Manager (SSM) document.

Do not put provider credentials in Git, Terraform variables/state, Docker build
arguments, Docker images, GitHub variables, or command-line arguments. This
guide describes billable AWS actions, but no AWS operation is performed from
the repository. Review each Terraform plan and authorize apply separately.

## 1. Gather the values you will need

Choose and record:

- **AWS account and Region:** use one Region for EC2, SSM, and both parameters.
- **GitHub repository:** `OWNER/REPOSITORY`, on the `main` branch.
- **Docker Hub namespace:** create two public repositories, for example
  `NAMESPACE/rca-demo-frontend` and `NAMESPACE/rca-demo-backend`.
- **DuckDNS hostname:** a subdomain such as `NAME.duckdns.org`.
- **EC2 sizing evidence:** complete [sizing.md](sizing.md) before choosing
  `architecture`, `instance_type`, or `root_volume_size_gib`.
- **Public subnet:** a subnet in the default VPC with a route to an Internet
  Gateway. This design does not create a VPC or subnet.

Creating GitHub/Docker Hub accounts, repositories, and local configuration is
not an AWS infrastructure operation. AWS charges may apply once you create
EC2, EBS, and a public IPv4 address; check current pricing for your Region.

## 2. Prepare Docker Hub and GitHub

### Docker Hub

1. In Docker Hub, create the frontend and backend repositories and set both to
   **Public**. The EC2 host pulls without Docker Hub credentials.
2. Create a Docker Hub access token for publishing. Store the token securely;
   do not add it to this repository.

Creating public repositories and a token does not create AWS resources.

### GitHub Actions credentials

In the GitHub repository, open **Settings → Secrets and variables → Actions**.
Under **Secrets**, add:

- `DOCKERHUB_USERNAME`: Docker Hub account or publishing user.
- `DOCKERHUB_TOKEN`: the Docker Hub access token.

Do not put AWS access keys here. Deployment uses GitHub OIDC and short-lived
AWS credentials. Add the repository variables in Step 6 after Terraform has
created the infrastructure.

GitHub configuration does not create AWS resources.

## 3. Create the two provider parameters in AWS

In AWS Console, select the chosen Region, then open **Systems Manager →
Parameter Store → Create parameter**. Create each value as type **SecureString**,
tier **Standard**, using the default `aws/ssm` key:

| Parameter name | Value |
| --- | --- |
| `/rca-ai/demo/prod/GROQ_API_KEY` | Your Groq API key |
| `/rca-ai/demo/prod/CEREBRAS_API_KEY` | Your Cerebras API key |

Do not put the values in Terraform. The EC2 role can retrieve only these two
parameters through its SSM permissions. The AWS-managed `aws/ssm` key is shared
at account scope: other account principals that already have broad Parameter
Store read permission may also retrieve SecureString values. This setup does
not create a customer-managed KMS key.

Standard Parameter Store configuration has no EC2 cost. Check current AWS
pricing for any applicable Parameter Store/KMS charges in your account.

## 4. Configure DuckDNS manually

1. Sign in to DuckDNS and register the chosen subdomain.
2. Keep the DuckDNS token private. Do not add it to Terraform or GitHub.
3. You will set the A record to the Terraform `public_ip` output after EC2 is
   created. Repeat this manually if the public IPv4 changes after Stop/Start.

DuckDNS setup is external to AWS. Do not create a DuckDNS SSM parameter; this
deployment does not update DNS automatically.

## 5. Inspect GitHub OIDC, then configure and apply Terraform

### Install and authenticate the AWS CLI on Windows

Install AWS CLI v2 if needed. In PowerShell, configure the profile and verify
the account identity:

```powershell
aws configure sso --profile rca-demo
aws sso login --profile rca-demo
$env:AWS_PROFILE = "rca-demo"
$env:AWS_DEFAULT_REGION = "YOUR_REGION"
aws sts get-caller-identity
```

Confirm the account ID and Region are the ones you intend to use. Local CLI
setup does not create AWS resources.

### Check OIDC ownership before planning

In AWS Console, open **IAM → Identity providers** and search for
`token.actions.githubusercontent.com`:

- If it is absent, set `github_oidc_provider_ownership = "create"` in tfvars
  and leave `github_oidc_thumbprint = ""` to let AWS use its current OIDC
  behavior. A thumbprint is optional; if you choose to provide one, it must be
  exactly 40 hexadecimal characters.
- If it exists, set ownership to `external` and copy its provider ARN to
  `existing_github_oidc_provider_arn`, and leave the thumbprint empty.
  Terraform will reuse the provider and will not create a duplicate.

Do not manually create the GitHub OIDC provider, deployment role, EC2 role or
instance profile, security group, or SSM deployment document. Terraform owns
those resources. IAM console inspection is read-only.

### Profile and prepare Terraform

Follow [sizing.md](sizing.md) using Docker Desktop's Linux engine on the
Windows host. The current VM has no Docker runtime, so it cannot produce the
required sizing measurements. Do not guess the EC2 architecture, instance
type, or root disk size.

From the repository root in PowerShell, copy the example and open the working
directory:

```powershell
Copy-Item infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
Set-Location infra/terraform
```

Replace every placeholder in `terraform.tfvars`. Set:

- `aws_region` and the 12-digit `aws_account_id`.
- `architecture`, `instance_type`, and `root_volume_size_gib` from reviewed
  profile evidence.
- `public_subnet_id` from a public subnet in the default VPC.
- `proxy_subnet_cidr` to a private CIDR not used by the VPC or other Docker
  networks. The backend trusts forwarded client IP headers only from this
  dedicated Compose subnet.
- `github_repository` and the OIDC ownership values from the prior step.
- Both lowercase Docker Hub namespace/repository values.
- `demo_hostname` for the DuckDNS hostname.

Never put API keys, Docker Hub tokens, or DuckDNS tokens in tfvars. Terraform
uses local state under `infra/terraform`; keep state and plan files private and
back up the state securely.

Then run:

```powershell
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan
terraform show tfplan
```

Review the plan. Applying it creates the EC2 instance, encrypted gp3 root EBS,
security group, IAM roles/profile/policies, and fixed SSM document. These AWS
resources may incur charges. Only after you approve the plan, run:

```powershell
terraform apply tfplan
```

Save the Terraform outputs securely. Read them later from `infra/terraform`
with:

```powershell
terraform output -raw aws_region
terraform output -raw instance_id
terraform output -raw public_ip
terraform output -raw github_deploy_role_arn
```

These values populate the GitHub variables below. Back up
`infra/terraform/terraform.tfstate` after apply to encrypted storage you
control; never upload it to GitHub or a public location. Keep any plan files
private as well.

## 6. Wait for EC2 initialization and configure GitHub variables

Terraform creates EC2 and its security group with inbound ports 80 and 443
only. It does not create inbound SSH access. Cloud-init installs Docker and
Compose, writes the production configuration/scripts, checks the Ubuntu SSM
Agent, and retrieves the two provider keys into root-only files. The backend
receives them as Compose secrets and its entrypoint exports them only into the
backend process environment. Secret values are not printed by these scripts.

In AWS Console, open **Systems Manager → Fleet Manager → Managed nodes** and
wait for the instance to show **Online**. If it is not online, use the
troubleshooting section below; do not open SSH or port 8000.

Now open GitHub **Settings → Secrets and variables → Actions → Variables** and
add:

| Variable | Value |
| --- | --- |
| `AWS_REGION` | Terraform output `aws_region` |
| `AWS_DEPLOY_ROLE_ARN` | Terraform output `github_deploy_role_arn` |
| `EC2_INSTANCE_ID` | Terraform output `instance_id` |
| `DOCKERHUB_FRONTEND_REPOSITORY` | `NAMESPACE/rca-demo-frontend` |
| `DOCKERHUB_BACKEND_REPOSITORY` | `NAMESPACE/rca-demo-backend` |
| `RELEASE_ARCHITECTURE` | Profiled `amd64` or `arm64` |

The repository secrets from Step 2 must also exist before the first push to
`main`. These GitHub settings do not create AWS resources.

Point the DuckDNS A record to Terraform output `public_ip`. Wait for DNS to
resolve to that IP before expecting Caddy to obtain an HTTPS certificate.

## 7. Run the first deployment

The first deployment and all later deployments use the same path:

1. Push the reviewed application commit to `main`.
2. GitHub Actions runs backend and frontend checks.
3. After tests pass, it builds and publishes both images tagged with the full
   commit SHA. The deploy job looks up each published tag in Docker Hub,
   validates its SHA256 digest, and constructs immutable
   `repository@sha256:…` references directly before deployment.
4. The deploy job assumes the repository-restricted AWS role through OIDC and
   invokes only the fixed `RCA-Demo-Deploy` SSM document on `EC2_INSTANCE_ID`.
5. The EC2 script checks that each digest belongs to the configured repository,
   pulls both images, runs Compose `up -d --wait`, then checks HTTPS health.

Pull requests run CI only. A successful **build** means tests passed and images
were published; a failed **deploy** means the instance or SSM path was
unavailable or deployment/health failed. The workflow never starts EC2. If the
instance is stopped, start it manually and wait until SSM shows **Online**.

When the workflow reports success, open
`https://YOUR_SUBDOMAIN.duckdns.org/api/demo/health` and confirm it returns
`{"status":"ready"}`. Opening the website should show the prepared scenarios.

## 8. Deploy retries and ordinary Stop/Start

### Retry a failed deployment

In GitHub, open **Actions → RCA Demo CI/CD → the failed main-branch run**.
If tests and image publication succeeded but deploy failed, choose **Re-run
failed jobs** after EC2 is running and SSM is **Online**. GitHub reruns the
failed deployment job with the image outputs from that workflow run; it does
not require publishing a new image pair. If build did not complete, choose
**Re-run all jobs**. A new commit also runs the normal build and deployment
path. There is no release database, manual promotion flow, or automatic
rollback.

### Stop and start EC2

- **Stop:** AWS Console → **EC2 → Instances** → select the demo instance →
  **Instance state → Stop**. The public site becomes unavailable. EBS and
  related retained resources may continue to incur charges.
- **Start:** use **Instance state → Start**. Wait until SSM is **Online**.
  Check the new public IPv4 and update the DuckDNS A record manually if it
  changed.
- Containers use Docker restart policy `unless-stopped`, so Docker normally
  starts the same saved containers and image pair after the instance boots.

If those existing containers did not start, connect using **Systems Manager →
Session Manager** and run this block. It reads each existing container's saved
image reference from Docker metadata and starts those containers; it does not
pull a different image or recreate them:

```bash
set -euo pipefail
project=rca-demo
frontend_id="$(sudo docker ps -aq --filter "label=com.docker.compose.project=$project" --filter label=com.docker.compose.service=frontend | head -n 1)"
backend_id="$(sudo docker ps -aq --filter "label=com.docker.compose.project=$project" --filter label=com.docker.compose.service=backend | head -n 1)"
test -n "$frontend_id" && test -n "$backend_id"
frontend_image="$(sudo docker inspect --format '{{.Config.Image}}' "$frontend_id")"
backend_image="$(sudo docker inspect --format '{{.Config.Image}}' "$backend_id")"
sudo env FRONTEND_IMAGE="$frontend_image" BACKEND_IMAGE="$backend_image" \
  docker compose --env-file /etc/rca-demo/config.env \
  -f /etc/rca-demo/compose.prod.yaml start
sudo docker compose --env-file /etc/rca-demo/config.env \
  -f /etc/rca-demo/compose.prod.yaml ps
```

The `Config.Image` values retain the digest references used when those
containers were created. If either container is missing, use the GitHub
deployment workflow after SSM is online; do not guess image tags.

## 9. Logs, secret rotation, and troubleshooting

Use **Systems Manager → Session Manager**; no SSH port is available. Useful
commands:

```bash
sudo cloud-init status --long
sudo tail -n 100 /var/log/cloud-init-output.log
sudo systemctl status docker --no-pager
sudo docker compose --env-file /etc/rca-demo/config.env \
  -f /etc/rca-demo/compose.prod.yaml ps
sudo docker compose --env-file /etc/rca-demo/config.env \
  -f /etc/rca-demo/compose.prod.yaml logs --tail=100
```

Common issues:

- **Instance is not SSM Online:** confirm it is running, the IAM instance
  profile is attached, the Region is correct, and cloud-init completed. The
  instance needs outbound internet access for SSM, Docker Hub, and provider
  APIs.
- **Cloud-init failed to load credentials:** confirm both exact parameter
  names exist in the same Region and the EC2 role can read them. Then rerun
  `sudo /usr/local/bin/rca-demo-fetch-secrets` from Session Manager and retry
  the GitHub deployment.
- **Deploy cannot pull images:** verify both repositories are public, their
  repository names match Terraform/GitHub configuration, and the build job
  completed.
- **Health check fails:** inspect Compose status and logs, verify DuckDNS points
  to the current public IP, and confirm ports 80/443 are reachable. Never open
  SSH or backend port 8000 as a workaround.
- **Workflow says SSM delivery timed out:** start EC2 manually, wait until
  SSM is Online, then rerun the failed deployment job.

To rotate provider keys, update the corresponding SecureString values in
Parameter Store. In Session Manager, run:

```bash
sudo /usr/local/bin/rca-demo-fetch-secrets
sudo docker compose --env-file /etc/rca-demo/config.env \
  -f /etc/rca-demo/compose.prod.yaml up -d --force-recreate backend
```

The values are not included in command arguments. Compose reads the root-only
files and mounts them into the backend container.

## 10. Cleanup

Cleanup is destructive and may delete the instance and its root disk. First
inspect `terraform plan -destroy` in `infra/terraform`; after separate review
and authorization, run `terraform destroy`. This removes Terraform-owned EC2,
EBS, security group, IAM role/profile/policies, SSM deployment document, and
the GitHub OIDC provider only if Terraform created it.

Terraform does not remove the manually created SecureString parameters, Docker
Hub repositories/token, DuckDNS account/record, or GitHub secrets/variables.
Remove those separately if no longer needed. A shared OIDC provider selected
as `external` remains in the AWS account. Confirm the instance and related
billable resources are gone in the AWS Console after cleanup.
