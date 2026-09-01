# Monitoring

Two things to monitor here:

1. **ArgoCD itself** — built-in dashboard shows sync status, health, history.
   Optional: install the ArgoCD notifications controller to post Slack/webhook
   alerts on sync failures (`argocd-notifications-cm`).

2. **Argo Rollouts** — install the kubectl plugin and use its live dashboard:
   ```
   kubectl argo rollouts dashboard
   ```
   Open http://localhost:3100 to watch canary/blue-green progress in real time.

3. **App metrics** — kube-prometheus-stack + Grafana, wired via the
   ServiceMonitor in this folder (requires the app to expose /metrics).
