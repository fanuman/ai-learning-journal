# Day 32 - Kubernetes fundamentals: local cluster, self-healing, a real missing-data bug

**Date completed:** _(fill in)_

## What I learned

**Kubernetes exists to solve a problem Docker Compose never had to: running containers across
many machines, not just one.** Compose orchestrates containers on a single host you already
manage by hand. Kubernetes assumes a *cluster* of machines and continuously reconciles a declared
desired state against it - rescheduling failed containers, tracking which node has capacity,
giving containers a stable network identity as they move, and rolling out updates - none of which
is a single-host problem in the first place.

**The core objects, and why each one exists:**
- **Pod** - the smallest deployable unit (one or more tightly-coupled containers sharing network/
  storage). Rarely created directly.
- **Deployment** - wraps Pods with a live reconciliation loop: declare "3 replicas of this Pod
  spec" and Kubernetes continuously enforces it, replacing any Pod that dies without being asked
  to do so again. This is *not* Compose's `restart: always` (which only restarts a container in
  place) - a Deployment can reschedule onto a different node entirely, and the replacement is a
  genuinely new Pod, not the same one restarted.
- **Service** - a stable DNS name over a set of Pods, addressing the same "container network
  identity" problem ECS Fargate's `localhost`-sidecar trick only partially solved. Pods are
  ephemeral and get new IPs constantly; a Service doesn't change even as the Pods behind it do.

**The declarative model, confirmed by actually watching it work today**: you don't tell
Kubernetes "restart this container" - you declare desired state (a Deployment's replica count, a
Pod spec) and a controller continuously reconciles reality toward it, forever, not just once at
apply time. `kubectl apply` isn't a one-shot imperative command the way `terraform apply` mostly
is; it's closer to *registering* a desired state that keeps being enforced afterward.

**Local vs. production Kubernetes cost model, genuinely different from ECS**: Minikube is free -
a single-node cluster running on your own machine, useful for exactly this kind of learning
exercise. Production-managed Kubernetes (AWS EKS) charges a flat **$0.10/hour per cluster for the
control plane alone** (~$73/month, continuous, regardless of workload) - a real difference from
ECS/Fargate's no-separate-cluster-fee model, and directly relevant to this project's established
"destroy between sessions" cost discipline once Day 33 (EKS) actually stands one up.

## Today's exercise

Installed `minikube` + `kubectl` via Homebrew (a slow one - an outdated Xcode Command Line Tools
version meant no precompiled bottle matched, so several dependencies built from source, 40+
minutes total; two non-fatal `brew link` conflicts at the end - a `kubectl` symlink clash with
Docker Desktop's own bundled copy, and a bash-completion file - neither affected the actual
binaries). Started a local single-node cluster:
```bash
minikube start
```

Wrote three Deployment+Service manifest pairs under `infra/k8s/` - `redis.yaml`, `chroma.yaml`,
`app.yaml` - mirroring the same three-container shape already defined in `docker-compose.yml` and
`infra/terraform/ecs.tf`. The one genuinely new piece versus both of those: `app.yaml` addresses
its dependencies as `CHROMA_HOST: "chroma"` / `REDIS_HOST: "redis"` - real Kubernetes Service DNS
names - rather than Compose's own `"redis"`/`"chroma"` (Compose's built-in DNS) or ECS's
`"localhost"` (containers sharing one Fargate task's network interface). Three different
container-runtime environments, three different answers to the same "how do sibling containers
find each other" question. The OpenAI key came from a Kubernetes Secret:
```bash
kubectl create secret generic openai-secret --from-literal=OPENAI_API_KEY=...
```
read into the app container via `secretKeyRef` - conceptually the same idea as ECS's Secrets
Manager injection, just Kubernetes' own native mechanism instead of an AWS-specific one.

## Two real problems hit and fixed, not scripted

**1. `docker build` failed against Minikube's Docker daemon** - `eval $(minikube docker-env)`
followed by a normal `docker build` errored with `404 page not found` while "booting buildkit."
Root cause: this Minikube cluster runs the newer `containerd` runtime by default, and
`minikube docker-env` faking a Docker socket over that is explicitly flagged by Minikube itself as
"highly experimental." Fix: skip `docker-env` + `docker build` entirely and use Minikube's own
build path instead, which works regardless of the underlying runtime:
```bash
minikube image build -t production-rag-agent:local -f infra/Dockerfile .
```

**2. A real, previously-invisible gap: the Dockerfile never copied `data/` into the image at
all.** `docker-compose.yml` bind-mounts `./data` from the host, which silently papered over this
the entire project - the image itself has never actually contained the product catalog. Only
surfaced today because Kubernetes has no equivalent to a host bind mount: a Pod runs inside the
cluster, with zero access to the Mac's filesystem. Confirmed directly:
```bash
kubectl exec -it deploy/app -- ls -la /app/data
# ls: cannot access '/app/data': No such file or directory
```
which explained an earlier `ValueError: Expected Embeddings to be non-empty list ... got []`
during ingestion - zero data files found, zero chunks, zero embeddings to add. Fixed with one
added line in `infra/Dockerfile`:
```dockerfile
COPY src/ ./src/
COPY data/ ./data/
```
**A real open question this raises**: since the exact same Dockerfile builds the production ECS
image, it's worth checking whether the ECS deployment has quietly had this same gap the whole
time, only ever masked by however ingestion actually happened there. Not chased down today -
flagged for later.

**A genuine Kubernetes gotcha surfaced by the rebuild**: re-running `minikube image build` with
the same tag does *not* make an already-running Pod pick up the new image - `imagePullPolicy`
defaults to `IfNotPresent` for any tag other than `latest`, so a live Pod just keeps its old image
indefinitely. Had to explicitly force a new Pod:
```bash
kubectl rollout restart deployment/app
```

## A live demonstration of the startup-ordering gap Compose's `depends_on` doesn't solve

Right after `kubectl apply`, the `app` Pod crash-looped several times
(`redis.exceptions.ConnectionError: ... connecting to redis:6379. Connection refused.`) while
Redis and Chroma were still mid-image-pull (`ContainerCreating`). Not a bug - `RAGPipeline`
connects to both at startup, and Kubernetes had no way to know Redis wasn't *ready* yet, only that
its Pod had been scheduled. Compose's `depends_on` has this exact same limitation (it controls
start order, not readiness) - Kubernetes' actual fix for this (readiness probes + `initContainers`)
wasn't built today, just observed and understood. Once both dependencies genuinely finished
starting, the `app` Pod's next automatic restart succeeded on its own - no manual intervention
needed, which is itself the underlying self-healing mechanism already doing its job.

## Test results

**Full pipeline, working end-to-end on Kubernetes:**
```bash
curl -X POST http://127.0.0.1:<minikube-tunnel-port>/ask \
  -H "Content-Type: application/json" -d '{"message": "What is the return policy?"}'
```
```json
{"reply":"The return policy allows most items to be returned within 30 days...",
 "sources":["returns_policy.txt"], "used_fallback":false, "from_cache":false}
```
Correctly grounded, real sources, no fallback - confirming retrieval, embeddings, Chroma, and the
full agent loop all work identically to Compose once the missing-data bug was actually fixed.

**Self-healing, demonstrated directly rather than just described:**
```bash
kubectl delete pod app-5f4bb747d5-wksj4
kubectl get pods -w
# app-5f4bb747d5-d9xqv   1/1   Running   0   7s
```
A replacement Pod was `Running` again within 7 seconds of deletion, with zero manual action beyond
watching it happen - the Deployment's reconciliation loop doing exactly what it's declared to do.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether the ECS production deployment has the same missing-`data/`-in-image gap, and if so, how
  ingestion there has actually been working
- What a real readiness-probe + `initContainers` fix for the startup-ordering problem would look
  like, versus just tolerating the crash-loop-then-recover behavior seen today

## Practice task
Stood up a local Minikube cluster and deployed the three-container stack (`app`, `chroma`,
`redis`) as Kubernetes Deployments + Services, translating Compose's DNS-name assumptions
(`"redis"`/`"chroma"`) into Kubernetes Service names and ECS's Secrets-Manager-injection pattern
into a native Kubernetes Secret. Hit and resolved two genuine problems along the way rather than
following a scripted happy path: a Minikube/containerd-specific `docker build` failure (fixed via
`minikube image build`), and a real, previously-undetected bug where the Dockerfile never actually
copied `data/` into the image at all - only ever masked by Compose's bind mount, and only surfaced
because Kubernetes Pods have no equivalent access to the host filesystem. Watched the app crash-
loop against not-yet-ready dependencies and recover on its own once they came up, then confirmed
the deployment fully works end-to-end with a real grounded RAG answer, and demonstrated self-
healing directly by deleting a Pod and watching Kubernetes replace it in 7 seconds.