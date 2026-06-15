// Scaling Phase 6 (readme/SCALABILITY_PLAN.md) — 50 concurrent-user read load test (T-1 / T-4).
//
// Proves: 50 simultaneous reviewer/admin sessions hitting the hot read paths stay under
// p95 < 400 ms with no 5xx. Exercises exactly the endpoints Phase 3 optimised (cached
// dashboards, de-N+1'd analytics, paginated queues).
//
// Run (needs the Java app up + a DB seeded to ~5,000 docs — see README):
//   BASE_URL=http://localhost:8080 \
//   LOGIN_USER=dhoteharshal16@gmail.com LOGIN_PASS='Admin123!' \
//   k6 run scripts/loadtest/read_50vu.js
//
// Auth assumption: POST /api/auth/authenticate returns a JWT in the body (field `token`
// or `accessToken`) AND/OR sets an auth cookie. We capture both and send the bearer
// header; if your build is cookie-only, the per-VU cookie jar still carries it.

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Trend } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const USER = __ENV.LOGIN_USER || 'dhoteharshal16@gmail.com';
const PASS = __ENV.LOGIN_PASS || 'Admin123!';

const loginTrend = new Trend('login_duration', true);

export const options = {
  scenarios: {
    fifty_users: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 50 },  // ramp to 50 concurrent users
        { duration: '3m',  target: 50 },  // hold
        { duration: '15s', target: 0 },   // ramp down
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    http_req_failed:   ['rate<0.01'],                 // < 1% errors (T-1: no 5xx)
    http_req_duration: ['p(95)<400'],                 // T-4: p95 < 400 ms overall
    'http_req_duration{group:::reviewer-queue}': ['p(95)<400'],
    'http_req_duration{group:::dashboards}':     ['p(95)<400'],
  },
};

function authHeaders() {
  const res = http.post(`${BASE}/api/auth/authenticate`,
    JSON.stringify({ username: USER, email: USER, password: PASS }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'login' } });
  loginTrend.add(res.timings.duration);
  check(res, { 'login 2xx': (r) => r.status >= 200 && r.status < 300 });
  let token = '';
  try { const b = res.json(); token = b.token || b.accessToken || b.jwt || ''; } catch (e) { /* cookie-only */ }
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function () {
  // Each VU authenticates on its first iteration; the cookie jar + bearer persist.
  const headers = authHeaders();
  const opts = { headers };

  group('reviewer-queue', () => {
    http.get(`${BASE}/api/reviewer/qc/results/pending?page=0&size=20`, { ...opts, tags: { name: 'pending-queue' } });
    http.get(`${BASE}/api/reviewer/qc/results/submitted`,            { ...opts, tags: { name: 'submitted-queue' } });
  });

  group('dashboards', () => {
    http.get(`${BASE}/api/analytics/overview?days=30`, { ...opts, tags: { name: 'analytics-overview' } });
    http.get(`${BASE}/api/analytics/ocr?days=30`,      { ...opts, tags: { name: 'analytics-ocr' } });
    http.get(`${BASE}/api/analytics/ml?days=30`,       { ...opts, tags: { name: 'analytics-ml' } });
    http.get(`${BASE}/api/admin/batches?page=0&size=20`, { ...opts, tags: { name: 'admin-batches' } });
  });

  sleep(Math.random() * 2 + 1); // 1–3s think time between user actions
}
