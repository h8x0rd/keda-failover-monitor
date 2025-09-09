
import os, time, re
from flask import Flask, jsonify
import requests
from threading import Lock

app = Flask(__name__)

# ---- Config via env ----
SITE_A_HEALTH_URL = os.getenv("SITE_A_HEALTH_URL", "").strip()
SITE_B_HEALTH_URL = os.getenv("SITE_B_HEALTH_URL", "").strip()
PROBE_METHOD       = os.getenv("PROBE_METHOD", "GET").upper()   # GET or HEAD
PROBE_TIMEOUT_SEC  = float(os.getenv("PROBE_TIMEOUT_SEC", "3"))
VERIFY_TLS         = os.getenv("VERIFY_TLS", "true").lower() == "true"
EXTRA_HEADER_KEY   = os.getenv("EXTRA_HEADER_KEY", "").strip()
EXTRA_HEADER_VAL   = os.getenv("EXTRA_HEADER_VAL", "").strip()
STATUS_REGEX       = os.getenv("ACCEPT_STATUS_REGEX", r"^2\d\d$")
CACHE_TTL_SEC      = float(os.getenv("CACHE_TTL_SEC", "5"))

_session = requests.Session()
_hdrs = {}
if EXTRA_HEADER_KEY and EXTRA_HEADER_VAL:
    _hdrs[EXTRA_HEADER_KEY] = EXTRA_HEADER_VAL

_cache = {"a": {"ts": 0, "down": True}, "b": {"ts": 0, "down": True}}
_lock = Lock()

def _is_ok(status_code: int) -> bool:
    return re.match(STATUS_REGEX, str(status_code)) is not None

def _probe(url: str) -> bool:
    """Return True if peer is DOWN."""
    if not url:
        return True
    try:
        if PROBE_METHOD == "HEAD":
            r = _session.head(url, timeout=PROBE_TIMEOUT_SEC, verify=VERIFY_TLS, headers=_hdrs)
        else:
            r = _session.get(url, timeout=PROBE_TIMEOUT_SEC, verify=VERIFY_TLS, headers=_hdrs)
        return not _is_ok(r.status_code)
    except Exception:
        return True

def _cached_probe(key: str, url: str) -> bool:
    now = time.time()
    with _lock:
        entry = _cache[key]
        if now - entry["ts"] <= CACHE_TTL_SEC:
            return entry["down"]
        down = _probe(url)
        entry["down"] = down
        entry["ts"] = now
        return down

@app.get("/metric/site-a")
def metric_site_a():
    # value for Site A's scaler (check peer Site B)
    peer_down = _cached_probe("b", SITE_B_HEALTH_URL)
    return jsonify(value=1 if peer_down else 0)

@app.get("/metric/site-b")
def metric_site_b():
    # value for Site B's scaler (check peer Site A)
    peer_down = _cached_probe("a", SITE_A_HEALTH_URL)
    return jsonify(value=1 if peer_down else 0)

@app.get("/healthz")
def healthz():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
