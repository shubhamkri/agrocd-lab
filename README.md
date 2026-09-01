# ArgoCD GitOps Lab

A single project that touches every piece on your list: Docker, Kubernetes,
Kind, GitHub + GitHub Actions, Argo CD, ApplicationSet, AppProject, Helm,
Kustomize, Secrets, sync waves, hooks, auto-sync, self-heal, pruning,
rollback, Argo Rollouts (canary + blue-green), and monitoring.

The app itself is intentionally trivial (a Flask "hello" service that prints
its version/color) — the point is the pipeline around it, not the app.

```
argocd-lab/
├── app/                        # Flask app + Dockerfile
├── .github/workflows/          # CI: build image, push to GHCR, bump manifest
├── k8s/base/                   # Kustomize base: Deployment, Service, ConfigMap, Secret
├── k8s/overlays/dev|staging/   # Kustomize overlays (per-env patches)
├── k8s/hooks/                  # PreSync/PostSync hook Jobs (sync waves)
├── helm/myapp/                 # Same app as a Helm chart (parallel path)
├── argocd/appproject.yaml      # AppProject (guardrails: repos, namespaces)
├── argocd/applicationset-*.yaml# ApplicationSets (kustomize path + helm path)
├── argocd/rollouts/            # Argo Rollouts: canary + blue-green
├── monitoring/                 # Prometheus/Grafana + Rollouts dashboard notes
└── kind-cluster.yaml           # 3-node local cluster config
```

---

## 0. Prerequisites

Install: `docker`, `kind`, `kubectl`, `helm`, `kustomize` (or use kubectl's
built-in `-k`), and the `kubectl argo rollouts` plugin.

```bash
brew install kind kubectl helm kustomize argoproj/tap/kubectl-argo-rollouts
# (or use your distro's package manager / binary releases)
```

Push this whole folder to a **new GitHub repo** (e.g. `argocd-lab`), then
replace every `YOUR_GH_USER` placeholder in the YAML/Helm files with your
actual GitHub username, and commit.

```bash
cd argocd-lab
grep -rl "YOUR_GH_USER" . | xargs sed -i '' 's/YOUR_GH_USER/<your-username>/g'   # macOS
# grep -rl "YOUR_GH_USER" . | xargs sed -i 's/YOUR_GH_USER/<your-username>/g'    # Linux
git init && git add . && git commit -m "init"
git branch -M main
git remote add origin https://github.com/<your-username>/argocd-lab.git
git push -u origin main
```

---

## 1. Create the Kind cluster

```bash
kind create cluster --config kind-cluster.yaml
kubectl cluster-info --context kind-argocd-lab
```

## 2. Install Argo CD

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

kubectl -n argocd rollout status deploy/argocd-server

# Get the initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d; echo

# Access the UI (in another terminal)
kubectl -n argocd port-forward svc/argocd-server 8081:443
# open https://localhost:8081  (user: admin)
```

Login via CLI too (handy later for rollback demos):

```bash
argocd login localhost:8081 --username admin --password <pw-from-above> --insecure
```

## 3. Install Argo Rollouts + its kubectl plugin dashboard

```bash
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml
kubectl -n argo-rollouts rollout status deploy/argo-rollouts
```

---

## 4. AppProject — the guardrails

`argocd/appproject.yaml` restricts this lab to one git repo and to
`myapp-*` namespaces only. Apply it first — ApplicationSets below reference
`project: lab-project`.

```bash
kubectl apply -f argocd/appproject.yaml
```

## 5. ApplicationSet — generate Applications per environment

Two ApplicationSets are included so you can compare the two deployment
techs side by side:

- `applicationset-kustomize.yaml` → generates `myapp-dev` / `myapp-staging`
  Applications, each pointing at a Kustomize overlay.
- `applicationset-helm.yaml` → generates `myapp-helm-dev` /
  `myapp-helm-staging`, each pointing at the Helm chart with a different
  `values-*.yaml`.

Both use a **list generator** (simplest kind). Apply them:

```bash
kubectl apply -f argocd/applicationset-kustomize.yaml
kubectl apply -f argocd/applicationset-helm.yaml

argocd app list
```

Within a minute you should see 4 Applications auto-created and syncing —
this is `automated: { prune: true, selfHeal: true }` doing its job
(**auto-sync**, **self-healing**, **pruning** all live here).

## 6. Watch sync waves + hooks in action

The `k8s/hooks/` folder (wired into the **dev** overlay only) contains:

- `db-migration` — `PreSync` hook, `sync-wave: "-1"` → runs **before**
  the Deployment/Service.
- `smoke-test` — `PostSync` hook, `sync-wave: "2"` → runs **after**
  everything is healthy, curls `/healthz`.

```bash
kubectl -n myapp-dev get jobs
kubectl -n myapp-dev logs job/db-migration
argocd app get myapp-dev   # shows the wave-ordered sync operation
```

## 7. Trigger the full CI/CD loop

Set a GitHub Actions secret if your registry needs one (GHCR with the
built-in `GITHUB_TOKEN` works out of the box, just make sure the repo's
**package visibility** is set correctly and Settings → Actions → General →
"Workflow permissions" is "Read and write").

Push any change under `app/` (e.g. edit the message string in `app.py`):

```bash
git add app/src/app.py
git commit -m "feat: tweak message"
git push
```

Watch the Actions tab: it builds+pushes the image to GHCR, then **commits
back to `k8s/overlays/dev/kustomization.yaml`** with the new image tag —
that git commit is what Argo CD detects and auto-syncs. This is the whole
GitOps loop: `code push → image build → manifest update → cluster sync`,
with no human touching `kubectl apply`.

## 8. Prove self-healing and pruning

**Self-heal** — manually break the live state, watch Argo CD revert it:

```bash
kubectl -n myapp-dev scale deploy/myapp --replicas=5
# within ~3 min (or immediately if you click "Refresh" in the UI) it snaps back to the git-defined replica count
```

**Pruning** — delete a resource from git, watch it get deleted from the cluster:

```bash
# comment out configMapGenerator in k8s/overlays/dev/kustomization.yaml, commit, push
# Argo CD removes the orphaned ConfigMap automatically because prune: true
```

## 9. Rollback

Two ways to roll back:

```bash
# A) Argo CD history/rollback (reverts the whole Application to a prior sync)
argocd app history myapp-dev
argocd app rollback myapp-dev <REVISION_ID>

# B) The GitOps-correct way: git revert the bad commit and push.
# Argo CD will auto-sync to the reverted state — this is the preferred method
# since it keeps git as the single source of truth.
git revert <bad-commit-sha>
git push
```

---

## 10. Argo Rollouts — Canary (staging)

This swaps the plain Deployment for a `Rollout` resource with a
progressive canary strategy (20% → 50% → 100%, with pauses and an
AnalysisTemplate health check between steps).

```bash
kubectl create namespace myapp-staging --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f argocd/rollouts/analysistemplate.yaml
kubectl apply -f argocd/rollouts/canary-rollout.yaml

kubectl argo rollouts get rollout myapp-canary -n myapp-staging --watch
```

Trigger a new rollout by bumping the image tag, then watch it step through
weights automatically (or control it manually):

```bash
kubectl argo rollouts set image myapp-canary myapp=ghcr.io/<you>/argocd-lab-app:sha-xxxxxxx -n myapp-staging
kubectl argo rollouts promote myapp-canary -n myapp-staging   # skip current pause
kubectl argo rollouts abort myapp-canary -n myapp-staging     # rollback if it's bad
```

## 11. Argo Rollouts — Blue-Green (prod)

Two Services (`myapp-active`, `myapp-preview`) sit in front of one Rollout.
New pods come up under `myapp-preview` first so you can test them before
flipping live traffic.

```bash
kubectl create namespace myapp-prod --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f argocd/rollouts/bluegreen-rollout.yaml

kubectl argo rollouts get rollout myapp-bluegreen -n myapp-prod --watch
```

```bash
kubectl argo rollouts set image myapp-bluegreen myapp=ghcr.io/<you>/argocd-lab-app:sha-xxxxxxx -n myapp-prod
# check the preview service manually, then:
kubectl argo rollouts promote myapp-bluegreen -n myapp-prod   # flips active -> new version
kubectl argo rollouts undo myapp-bluegreen -n myapp-prod      # rollback to previous
```

> To have Argo CD manage these Rollouts too (rather than `kubectl apply`),
> point another Application/ApplicationSet entry at `argocd/rollouts/`.

---

## 12. Monitoring

```bash
kubectl argo rollouts dashboard   # live canary/blue-green visualization on :3100

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace -f monitoring/kube-prometheus-stack-values.yaml
kubectl apply -f monitoring/servicemonitor.yaml
```

See `monitoring/README.md` for details on wiring Grafana + ArgoCD notifications.

---

## 13. Secrets — a note

`k8s/base/secret.yaml` is a **plain Kubernetes Secret committed to git**,
which is fine for a local lab but never for real use (git history keeps
"deleted" secrets forever). For production GitOps, swap it for one of:

- **Sealed Secrets** (Bitnami) — encrypt secrets client-side, safe to commit.
- **External Secrets Operator** — pulls from AWS/GCP/Vault secret managers.
- **SOPS + age/KMS** — encrypt the YAML file itself, decrypt at apply time.

---

## Cleanup

```bash
kind delete cluster --name argocd-lab
```

## What maps to what (quick reference)

| Concept          | Where |
|-------------------|-------|
| Docker            | `app/Dockerfile` |
| Kubernetes        | `k8s/base/*.yaml` |
| Kind              | `kind-cluster.yaml` |
| GitHub Actions    | `.github/workflows/ci-cd.yaml` |
| Argo CD           | Steps 2–9 |
| ApplicationSet    | `argocd/applicationset-*.yaml` |
| AppProject        | `argocd/appproject.yaml` |
| Helm              | `helm/myapp/` |
| Kustomize         | `k8s/base/`, `k8s/overlays/` |
| Secrets           | `k8s/base/secret.yaml` (+ Section 13) |
| Sync waves        | `k8s/hooks/*` annotations |
| Hooks             | `k8s/hooks/*` |
| Auto-sync/self-heal/prune | `syncPolicy.automated` in the ApplicationSets |
| Rollback          | Section 9 |
| Argo Rollouts     | `argocd/rollouts/` |
| Canary            | `argocd/rollouts/canary-rollout.yaml` |
| Blue-Green        | `argocd/rollouts/bluegreen-rollout.yaml` |
| Monitoring        | `monitoring/` |
# agrocd-lab
