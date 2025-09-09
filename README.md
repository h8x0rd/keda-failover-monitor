
# Failover Monitor (Flask) for KEDA metrics-api

A tiny Flask service you can run **outside** both clusters. It checks each site's app health URL and exposes
KEDA-friendly JSON metrics:

- `GET /metric/site-a` → returns `{"value": 1}` if **Site B is down**, else `0`
- `GET /metric/site-b` → returns `{"value": 1}` if **Site A is down**, else `0`
- `GET /healthz`       → monitor's own health

Point each cluster's KEDA ScaledObject to the relevant endpoint.

---

## Quick start (container via Podman)

```bash
# 1) Build
podman build -t failover-monitor:latest .

# 2) Copy and edit env file
cp env.example .env
# edit .env values to your routes/URLs

# 3) Run
podman run -d --name failover-monitor -p 8000:8000 --env-file .env failover-monitor:latest

# 4) Test
curl -s http://localhost:8000/metric/site-a
curl -s http://localhost:8000/metric/site-b
curl -s http://localhost:8000/healthz
```

### Generate a systemd unit (Podman-managed)
```bash
podman stop failover-monitor || true
podman rm failover-monitor || true
podman run -d --name failover-monitor --restart=always -p 8000:8000 --env-file .env failover-monitor:latest
podman generate systemd --new --files --name failover-monitor
sudo mv container-failover-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now container-failover-monitor
```

---

## Quick start (bare metal via venv + gunicorn)

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# Export envs (or `cp env.example .env` and `set -a; source .env; set +a`)
export SITE_A_HEALTH_URL="https://my-app-my-app.apps.site-a.example.com/healthz"
export SITE_B_HEALTH_URL="https://my-app-my-app.apps.site-b.example.com/healthz"
export PROBE_METHOD="GET"
export PROBE_TIMEOUT_SEC="3"
export VERIFY_TLS="true"
export CACHE_TTL_SEC="5"

gunicorn -w 2 -b 0.0.0.0:8000 app:app
```

### systemd unit (venv)
1) Adjust the paths in `systemd/failover-monitor-venv.service`.  
2) Copy and enable:
```bash
sudo cp systemd/failover-monitor-venv.service /etc/systemd/system/
sudo cp env.example /etc/failover-monitor.env  # or your own env file
sudo systemctl daemon-reload
sudo systemctl enable --now failover-monitor-venv
```

---

## KEDA ScaledObjects (templates)

In Site **A** (scale to 4 when **Site B** is down):
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: my-app-failover
  namespace: my-app
spec:
  scaleTargetRef:
    kind: Deployment
    name: my-app
  minReplicaCount: 2
  maxReplicaCount: 4
  pollingInterval: 15
  cooldownPeriod: 120
  triggers:
  - type: metrics-api
    metadata:
      method: "GET"
      url: "http://<monitor-host>:8000/metric/site-a"
      valueLocation: "value"
      threshold: "1"
      activationThreshold: "0"
```

In Site **B** (scale to 4 when **Site A** is down):
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: my-app-failover
  namespace: my-app
spec:
  scaleTargetRef:
    kind: Deployment
    name: my-app
  minReplicaCount: 2
  maxReplicaCount: 4
  pollingInterval: 15
  cooldownPeriod: 120
  triggers:
  - type: metrics-api
    metadata:
      method: "GET"
      url: "http://<monitor-host>:8000/metric/site-b"
      valueLocation: "value"
      threshold: "1"
      activationThreshold: "0"
```

> If your monitor is served over HTTPS with a trusted cert, change the URLs to `https://…`.

---

## Security / TLS
- For peer routes using private CAs, either:
  - Terminate TLS at a public LB in front of the monitor, or
  - Bake the CA into the image and set `REQUESTS_CA_BUNDLE=/etc/ssl/certs/custom-ca.crt` at runtime.
- To send an auth header to the peer’s health URL, set `EXTRA_HEADER_KEY=Authorization` and `EXTRA_HEADER_VAL="Bearer <token>"`.

## Tuning
- `cooldownPeriod` in ScaledObjects reduces scale-down flapping.
- `CACHE_TTL_SEC` reduces probe chattiness (default 5s).

MIT License.
