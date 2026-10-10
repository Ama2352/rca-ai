# RCA Demo host sizing evidence

This procedure measures the production frontend/backend image pair and the
backend's offline analysis workload before selecting an EC2 architecture,
instance type, or root-volume size. It does not contact AWS or either LLM
provider. It does not select an instance or alter Terraform variables.

## Prerequisites

1. Use the host that owns the **Linux-container Docker Engine**. Docker Desktop on
   Windows must be switched to Linux containers and running. The VM's Docker
   socket is not required; run the collector on the Windows host, where the
   Docker CLI reaches Docker Desktop's Linux engine. Do not run this inside the
   Vagrant VM unless that VM has a working Docker Engine socket.
2. Install Python 3.12 and Docker Desktop, start Docker Desktop, and verify in
   PowerShell:

   ```powershell
   docker version
   docker info --format '{{.OSType}} {{.Architecture}}'
   ```

   The server must report `linux`. Record the reported engine architecture.
3. Ensure neither `GROQ_API_KEY` nor `CEREBRAS_API_KEY` is set in the shell
   environment. The profiler aborts before invoking Docker if either is
   nonempty. Do not put provider keys in command arguments or profile output.
4. Build local images only; do not push them:

   ```powershell
   docker build -f Dockerfile.prod -t rca-demo-backend:profile .
   docker build -f frontend/Dockerfile.prod -t rca-demo-frontend:profile frontend
   ```

   The backend build context excludes `scripts/`; the collector bind-mounts the
   offline harness read-only into a temporary container. The harness is not
   part of either production image or `compose.prod.yaml`.

## Run the profile

From the repository root in PowerShell, run:

```powershell
py scripts/profile_production.py `
  --compose compose.prod.yaml `
  --backend-image rca-demo-backend:profile `
  --frontend-image rca-demo-frontend:profile `
  --trials 3 `
  --output .\artifacts\rca-profile.json
```

The command creates a disposable backend and frontend (Caddy) container per
trial on an isolated Docker network. The backend exposes the `backend` network
alias expected by Caddy; the workload is sent through Caddy to the backend. It
waits for cold start, reads the incident catalog, performs one complete offline
analysis of each of the nine prepared scenarios using a fake Generator,
restarts the backend, and verifies readiness through Caddy again. A background
sampler captures both containers' Docker stats at one-second intervals. Memory
is the sum of the two containers' current memory at each sample; CPU is the sum
of their Docker CPU percentages for that sample. Reported peaks are the maximum
combined sample across the trial(s), not the sum of unrelated peaks at
different times. If any stats command fails or a container row is missing,
the trial fails and no profile is written. The API/Facts/retrieval/assembly
work runs, while provider network calls are never made.

The image report includes Docker's unpacked image size and a gzip-compressed
`docker image save` archive size. The latter is a local archive estimate, not
an exact Docker Hub wire-transfer measurement. Both image architectures must
match. The disk estimate counts the currently running image pair and the next
pair being pulled, without relying on layer deduplication.

The result's `required_volume_bytes_with_25pct_free` includes the replacement
peak image estimate and `--existing-used-bytes`, divided by 0.75. On a new EC2 instance,
measure or estimate the base OS and Docker overhead on a representative Ubuntu
24.04 host before treating this as an EBS recommendation. The Windows Docker
Desktop VM's free space is not EC2 root-volume usage. To include a measured
target-host baseline, pass its used root bytes explicitly:

```powershell
py scripts/profile_production.py `
  --backend-image rca-demo-backend:profile `
  --frontend-image rca-demo-frontend:profile `
  --existing-used-bytes <measured-linux-root-used-bytes> `
  --output .\artifacts\rca-profile.json
```

The collector intentionally has no EC2 instance type, architecture, or root
volume default. The resulting report is evidence for review, not an automatic
Terraform input. Do not finalize those values until all three trials succeed,
all nine scenarios appear in every trial, architecture is confirmed, peak
memory has at least 1.3x headroom on a candidate, CPU is not persistently
saturated, and the chosen volume leaves at least 25% free after allowing for
the OS and a current-plus-replacement image pair. Check current On-Demand availability/pricing
separately after the offline measurements and before the user's AWS approval
gate.

## Current environment checkpoint

The Codex Vagrant VM currently has no Docker CLI/daemon socket, so no production
container measurements have been collected here. EC2 architecture, instance
type, and EBS size therefore remain unresolved. Run the commands above on the
Windows host's running Docker Desktop Linux engine and preserve the JSON report
for sizing review.
