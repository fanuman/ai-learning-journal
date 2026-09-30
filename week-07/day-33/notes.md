# Day 33 - Kubernetes on AWS: EKS fundamentals (conceptual walkthrough, not deployed)

**Date completed:** _(fill in)_

## What I learned

**EKS splits what Minikube gave for free into two separately-billed pieces.** Minikube's single
`minikube start` gave a full cluster (control plane + one worker node) running entirely on my own
machine, free. EKS separates that same idea: AWS runs and manages the **control plane** for a flat
**$0.10/hour** (~$73/month if left running continuously) regardless of what's deployed to it, and
**worker capacity** is billed separately - either real EC2 instances in a **managed node group**,
or per-Pod via **EKS Fargate profiles** (a different pricing model from ECS Fargate, despite the
shared name). For a small 3-Pod stack, a managed node group of a couple small EC2 instances is
simpler and cheaper than Fargate's per-Pod minimums.

**`eksctl` is doing a lot more than it looks like.** One command -
```bash
eksctl create cluster --name ... --region eu-north-1 --nodegroup-name standard-workers \
  --node-type t3.medium --nodes 2 --nodes-min 2 --nodes-max 2 --managed
```
- actually provisions: a dedicated VPC with public/private subnets across multiple AZs, an internet
gateway and NAT gateway, a separate IAM role for the control plane, a separate IAM role for the
worker nodes, the EKS control plane itself, and a real EC2 Auto Scaling Group as the managed node
group - plus it automatically updates the local `~/.kube/config` to point `kubectl` at the new
cluster. The same "one command replaces dozens of hand-declared resources" tradeoff Terraform gave
for ECS, just AWS's own purpose-built tool for Kubernetes specifically instead of a general IaC
tool.

**The worker-node IAM role is what makes ECR image pulls work with zero manual login.** EKS-
optimized AMIs ship a built-in ECR credential helper wired to the node's own IAM role - genuinely
different from Minikube, where `minikube image build` sidestepped the whole "where does the image
come from" question entirely by building straight into the cluster's own local Docker daemon. On
EKS, nodes are real EC2 instances with no access to a laptop at all, so the image has to already be
somewhere reachable - which is exactly what the project's existing ECR + CI/CD pipeline already is.
No new build step needed; just point `app.yaml`'s `image:` field at the real ECR URI
(`033307277379.dkr.ecr.eu-north-1.amazonaws.com/production-rag-agent:latest`) instead of
`production-rag-agent:local`.

**Secrets are per-cluster, not portable.** Minikube's `openai-secret` and an EKS cluster's
`openai-secret` would be two entirely separate objects, identical name and value or not - every
new cluster needs its own `kubectl create secret` run against it.

**`LoadBalancer` is a genuine step up from `NodePort` + a tunnel, not just a naming difference.**
Minikube's `NodePort` + `minikube service --url` was a local-only workaround for the fact that
nothing outside the Mac could reach the cluster anyway. On real AWS, changing the Service type to
`LoadBalancer` actually provisions a real Elastic Load Balancer with a genuine public DNS hostname
under `kubectl get service`'s `EXTERNAL-IP` column - no tunnel command needed, because it's
actually internet-reachable. That reachability is also exactly why it carries its own small hourly
cost (~$0.025/hr) independent of the cluster itself, and why the Service should be deleted before
tearing down the cluster rather than left for `eksctl delete cluster` to clean up implicitly.

**Self-healing has a second layer on EKS that Minikube structurally couldn't demonstrate.**
Minikube only ever had one node, so Day 32's demo could only show *Pod*-level self-healing (delete
a Pod, a Deployment replaces it). A managed node group's EC2 Auto Scaling Group adds a layer below
that: if an entire worker node died, the ASG would notice and launch a replacement node on its own
- infrastructure-level self-healing, not just container-level.

**Teardown mirrors Terraform's completeness, just for a different resource graph:**
```bash
kubectl delete service app          # release the ELB first
eksctl delete cluster --name production-rag-agent-eks --region eu-north-1
```
reverses everything `create cluster` built - node group, control plane, IAM roles, VPC - in one
command, same idea as `terraform destroy` for the ECS stack.

## A deliberate decision: conceptual walkthrough, not a live deployment

Explicitly chose not to actually create a real EKS cluster today. Reasoning, weighed openly rather
than defaulted into: Day 32 already covered the real Kubernetes concepts hands-on for free
(Pods, Deployments, Services, self-healing, a genuine crash-and-recover cycle, a real missing-data
bug found and fixed). Day 33's incremental value over that is narrower - mainly the AWS-specific
mechanics (managed control plane, node groups, IAM-for-Kubernetes, ECR-based image pulls, a real
LoadBalancer) and the EKS cost model specifically - both of which a precise command-by-command
walkthrough covers accurately, without spending real money or ~30-45 minutes on cluster
create/destroy cycles for a "fundamentals" day. Estimated real cost if run start-to-finish would
have been small (~$0.10-0.30 total), but the time cost was the bigger factor.

**What this means concretely**: no `production-rag-agent-eks` cluster exists, no EKS charges were
incurred, and nothing needs to be torn down. If a genuine hands-on EKS deployment becomes valuable
later (e.g., as part of the Week 7 Saturday project, or the Week 8 capstone's own infra work), the
exact commands above are the real, correct sequence to run - this wasn't skipped because it's
unclear how, just deliberately deferred.

## Questions / things that confused me
- _(fill in anything still fuzzy)_
- Whether the Week 7 Saturday project's EKS deployment step should be the first time this actually
  gets run for real, now that the conceptual groundwork is in place
- Whether EKS Fargate profiles would have actually been simpler than a managed node group for a
  stack this small, despite the per-Pod pricing model - not concretely compared today, just
  reasoned about from pricing structure alone

## Practice task
Walked through the complete command sequence for deploying to AWS EKS - cluster creation via
`eksctl` (and everything it provisions under the hood: VPC, IAM roles, control plane, managed node
group), recreating the OpenAI Secret in the new cluster, repointing `app.yaml` at the existing ECR
image instead of a local build, switching the Service type to `LoadBalancer` for real external
access, and the full teardown sequence - without actually creating live AWS infrastructure.
Deliberately scoped as a conceptual walkthrough rather than a hands-on deployment, since Day 32
already covered the underlying Kubernetes concepts for free and today's real incremental value was
narrowly the AWS-specific mechanics and cost model, both covered precisely without the time/cost of
an actual create-test-destroy cycle.