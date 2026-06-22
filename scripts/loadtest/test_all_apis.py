#!/usr/bin/env python3
"""
Exhaustive API test — every Java + Python endpoint + the interconnection.
  • READ (GET) endpoints: called AUTHENTICATED → expect 2xx (404 ok for missing id)
  • MUTATING/DESTRUCTIVE endpoints: called WITHOUT auth → expect 401/403/302 (proves
    the endpoint exists AND is protected) — we do NOT execute destructive actions or
    trigger Groq-heavy work.
  • Python: public (health/live) expect 200 no-key; everything else 401 without key,
    reachable with key.
"""
import json
import os
import re
import urllib.request
import urllib.error
import http.cookiejar

JAVA = "http://127.0.0.1:8080"
PY = "http://127.0.0.1:5001"
ADMIN = {"username": os.environ.get("LOGIN_USER", "harshal@eaglexinfo.com"),
         "password": os.environ.get("LOGIN_PASS", "Admin123!")}

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def req(url, method="GET", headers=None, data=None, use_cookie=False, timeout=12):
    h = headers or {}
    body = json.dumps(data).encode() if data is not None else None
    if body:
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, method=method, headers=h)
    o = opener if use_cookie else urllib.request.build_opener()
    try:
        resp = o.open(r, timeout=timeout)
        return resp.status, resp.read(2000000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return f"ERR:{type(e).__name__}", ""


def login():
    s, _ = req(f"{JAVA}/api/auth/authenticate", "POST", data=ADMIN, use_cookie=True)
    return s


def jget(path):
    return req(f"{JAVA}{path}", "GET", use_cookie=True)[0]


def jnoauth(path, method):
    return req(f"{JAVA}{path}", method)[0]


def main():
    import os
    KEY = ""
    for line in open(os.path.join(os.path.dirname(__file__), "../../.env")):
        if line.startswith("INTERNAL_API_KEY="):
            KEY = line.split("=", 1)[1].strip()
    print(f"login: HTTP {login()}")

    # discover ids
    bid = qrid = fid = uid = cid = None
    s, body = req(f"{JAVA}/api/admin/batches", use_cookie=True)
    try:
        items = json.loads(body)
        bid = items[0]["id"]
    except Exception:
        pass
    if bid:
        s, body = req(f"{JAVA}/api/qc/results/{bid}", use_cookie=True)
        try:
            arr = json.loads(body); arr = arr if isinstance(arr, list) else arr.get("results", [])
            qrid = arr[0]["id"]; fid = arr[0].get("batchFileId") or arr[0].get("batchFile", {}).get("id")
        except Exception:
            pass
    s, body = req(f"{JAVA}/api/admin/users", use_cookie=True)
    try:
        uid = json.loads(body)[0]["id"]
    except Exception:
        pass
    s, body = req(f"{JAVA}/api/admin/clients", use_cookie=True)
    try:
        arr = json.loads(body); cid = (arr if isinstance(arr, list) else arr.get("content", []))[0]["id"]
    except Exception:
        pass
    print(f"discovered: batch={bid} qcResult={qrid} file={fid} user={uid} client={cid}\n")

    def P(x, d):
        return str(x) if x is not None else d

    # ---- Java GET reads (authenticated) ----
    reads = [
        "/api/me", "/api/config/password-policy", "/api/admin/dashboard", "/api/admin/system/health",
        "/api/admin/batches", f"/api/admin/batches/{P(bid,'1')}", f"/api/admin/batches/{P(bid,'1')}/status",
        f"/api/admin/batches/{P(bid,'1')}/audit",
        "/api/admin/clients", "/api/admin/clients/stats", f"/api/admin/clients/{P(cid,'1')}",
        "/api/admin/users", f"/api/admin/users/{P(uid,'1')}",
        "/api/admin/doc-stats", "/api/admin/doc-stats/batches", "/api/admin/doc-stats/rules/ranking",
        "/api/admin/doc-stats/thresholds", "/api/admin/doc-stats/trend",
        f"/api/admin/doc-stats/{P(qrid,'1')}", f"/api/admin/doc-stats/{P(qrid,'1')}/compare",
        "/api/analytics/overview", "/api/analytics/trend", "/api/analytics/ocr", "/api/analytics/ml",
        "/api/analytics/operators", "/api/analytics/anomalies", "/api/analytics/review-sla",
        "/api/graph/overview", "/api/graph/search?q=x", f"/api/graph/batch/{P(bid,'1')}",
        f"/api/graph/file/{P(fid,'1')}", f"/api/graph/reviewer/{P(uid,'1')}",
        f"/api/graph/revisions/qcresult/{P(qrid,'1')}",
        "/api/qc/health", "/api/qc/rules", f"/api/qc/results/{P(bid,'1')}", f"/api/qc/progress/{P(bid,'1')}",
        f"/api/qc/findings/{P(bid,'1')}", f"/api/qc/file/{P(qrid,'1')}",
        f"/api/qc/history/file/{P(fid,'1')}", f"/api/qc/history/diff/{P(qrid,'1')}",
        "/api/reviewer/config", "/api/reviewer/dashboard", "/api/reviewer/qc/results/pending",
        "/api/reviewer/qc/results/submitted", "/api/reviewer/admin/overrides/pending",
        f"/api/reviewer/qc/{P(qrid,'1')}/result", f"/api/reviewer/qc/{P(qrid,'1')}/rules",
        f"/api/reviewer/qc/{P(qrid,'1')}/audit", f"/api/reviewer/qc/{P(qrid,'1')}/progress",
        f"/files/{P(fid,'1')}", "/profile",
    ]
    # ---- Java mutating/destructive (auth-protection probe only) ----
    mut = [
        ("POST", "/api/admin/batches/upload"), ("DELETE", f"/api/admin/batches/{P(bid,'1')}"),
        ("POST", f"/api/admin/batches/{P(bid,'1')}/assign"),
        ("POST", "/api/admin/clients"), ("POST", "/api/admin/users"),
        ("PUT", f"/api/admin/users/{P(uid,'1')}"), ("DELETE", f"/api/admin/users/{P(uid,'1')}"),
        ("POST", f"/api/admin/users/{P(uid,'1')}/reset-password"),
        ("POST", f"/api/admin/users/{P(uid,'1')}/status"),
        ("POST", f"/api/qc/process/{P(bid,'1')}"), ("POST", f"/api/qc/process/{P(bid,'1')}/files"),
        ("POST", f"/api/qc/cancel/{P(bid,'1')}"), ("POST", "/api/qc/reconcile"),
        ("POST", "/api/reviewer/decision/save"), ("POST", "/api/reviewer/decision/focus"),
        ("POST", f"/api/reviewer/qc/{P(qrid,'1')}/session/start"),
        ("POST", f"/api/reviewer/qc/{P(qrid,'1')}/session/heartbeat"),
        ("POST", f"/api/reviewer/qc/{P(qrid,'1')}/submit"),
        ("POST", f"/api/reviewer/qc/{P(qrid,'1')}/request-re-review"),
        ("POST", f"/api/reviewer/admin/overrides/{P(qrid,'1')}/decide"),
        ("POST", "/profile"), ("POST", "/profile/password"), ("POST", "/api/auth/register"),
    ]

    print("===== JAVA READS (authenticated) — expect 2xx, or 404 for a missing id =====")
    bad = []
    for p in reads:
        s = jget(p)
        flag = "" if (isinstance(s, int) and (200 <= s < 300 or s == 404)) else "  <-- CHECK"
        if flag: bad.append((p, s))
        print(f"  {str(s):4} GET  {p}{flag}")

    print("\n===== JAVA MUTATING (no-auth probe) — expect 401/403/302 (protected) =====")
    for m, p in mut:
        s = jnoauth(p, m)
        ok = isinstance(s, int) and s in (401, 403, 302)
        flag = "" if ok else "  <-- NOT PROTECTED?"
        if not ok: bad.append((p, s))
        print(f"  {str(s):4} {m:6} {p}{flag}")

    # ---- Python ----
    print("\n===== PYTHON — public (no key) + key-gated =====")
    pub = ["/health", "/live"]
    getk = ["/schema/fields", "/corrections", "/baseline/latest", "/routing/config", "/amc/profiles",
            "/qc/transactions"]
    for p in pub:
        s, _ = req(f"{PY}{p}")
        print(f"  {str(s):4} GET  {p} (public, expect 200){'' if s==200 else '  <-- CHECK'}")
    for p in getk:
        s0, _ = req(f"{PY}{p}")                       # no key -> 401
        s1, _ = req(f"{PY}{p}", headers={"X-API-Key": KEY})  # key -> 2xx
        ok = (s0 == 401) and isinstance(s1, int) and 200 <= s1 < 300
        print(f"  nokey={s0} key={s1} GET {p}{'' if ok else '  <-- CHECK'}")
    print("  --- Python mutating/Groq (no-key probe, expect 401) ---")
    for m, p in [("POST", "/qc/process"), ("POST", "/qc/submit"), ("POST", "/qc/transaction"),
                 ("POST", "/baseline/run"), ("POST", "/corrections"), ("PUT", "/routing/config"),
                 ("POST", "/schema/reload"), ("POST", "/validate/x")]:
        s, _ = req(f"{PY}{p}", m)
        print(f"  {str(s):4} {m:5} {p}{'' if s==401 else '  <-- CHECK (expect 401)'}")

    print(f"\n=== anomalies to review: {len(bad)} ===")
    for p, s in bad:
        print(f"   {s}  {p}")


if __name__ == "__main__":
    main()
