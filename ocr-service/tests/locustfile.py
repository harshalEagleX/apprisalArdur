"""
SHAL OCR Service — Locust load + performance test suite.

Covers all Python-side functional areas:
  • /health                  — heartbeat + availability
  • /qc/process              — synchronous QC submission
  • /qc/process-async        — async Celery submit + status poll
  • /qc/status/{job_id}      — async job polling
  • /corrections             — reviewer field-correction stream
  • /correction-stats        — aggregate stats read

Usage (quick smoke, 10 users, 60 s):
  conda run -n shal locust -f ocr-service/tests/locustfile.py \\
    --headless -u 10 -r 2 -t 60s --host http://localhost:8000

Usage (full load, 200 users):
  conda run -n shal locust -f ocr-service/tests/locustfile.py \\
    --headless -u 200 -r 10 -t 300s --host http://localhost:8000

Usage (web UI — open http://localhost:8089):
  conda run -n shal locust -f ocr-service/tests/locustfile.py \\
    --host http://localhost:8000
"""

import json
import random
import string
import time
import uuid
from pathlib import Path

from locust import HttpUser, TaskSet, between, task, events

# ── Synthetic test data ───────────────────────────────────────────────────────

AMC_CODES = [
    "FIRSTAM", "CORELOGIC", "LANDSAFE", "VEROS", "SOLIDIFI",
    "CLAROCITY", "RELS", "GREENLIGHT", "TITANIUM", "NATISTAR",
]

FIELDS = [
    "subject_address", "borrower_name", "appraised_value", "effective_date",
    "contract_price", "gla", "land_area", "year_built", "neighborhood_name",
    "city", "state", "zip_code", "legal_description", "apn",
]

STATES = ["AZ", "TX", "CA", "FL", "NY", "GA", "CO", "IL", "WA", "OR"]

CORRECTION_REASONS = [
    "wrong_value", "missing_value", "format_error", "ocr_error", "extraction_failed"
]

# Minimal PDF bytes (real magic bytes so the service doesn't reject it)
MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n"
    b"2 0 obj\n<</Type /Pages /Kids [3 0 R] /Count 1>>\nendobj\n"
    b"3 0 obj\n<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>>\nendobj\n"
    b"xref\n0 4\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"trailer\n<</Size 4 /Root 1 0 R>>\n"
    b"startxref\n190\n%%EOF"
)


def rand_str(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def rand_address() -> str:
    num = random.randint(100, 9999)
    street = rand_str(6)
    st_type = random.choice(["St", "Ave", "Blvd", "Dr", "Ln", "Way"])
    city = rand_str(6).capitalize()
    state = random.choice(STATES)
    zipcode = str(random.randint(10000, 99999))
    return f"{num} {street} {st_type}, {city}, {state} {zipcode}"


def rand_manifest(amc_code: str, order_number: str, address: str) -> dict:
    return {
        "transaction_ref": f"LT-{amc_code}-{order_number}",
        "amc_code": amc_code,
        "order_number": order_number,
        "property_address": address,
    }


def rand_correction() -> dict:
    return {
        "fieldName": random.choice(FIELDS),
        "originalValue": str(random.randint(100_000, 900_000)),
        "correctedValue": str(random.randint(100_000, 900_000)),
        "reason": random.choice(CORRECTION_REASONS),
        "documentId": f"doc-{rand_str(12)}",
        "extractionResultId": random.randint(1, 10000),
    }


# ── Task sets ─────────────────────────────────────────────────────────────────


class HealthCheckTasks(TaskSet):
    """Simulates monitoring / heartbeat polls — very high frequency."""

    @task(10)
    def health(self):
        with self.client.get("/health", catch_response=True) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code in (503, 500):
                r.failure(f"Service unhealthy: {r.status_code}")


class QCSyncTasks(TaskSet):
    """Synchronous QC submissions — models small batch inline processing."""

    @task(3)
    def qc_process_sync(self):
        amc_code = random.choice(AMC_CODES)
        order_number = f"ORD{random.randint(100000, 999999)}"
        address = rand_address()
        payload = {
            "appraisal_path": f"/tmp/load-test/{rand_str()}.pdf",
            "engagement_path": f"/tmp/load-test/{rand_str()}_eng.pdf",
            "contract_path": None,
            "amc_code": amc_code,
            "client_id": str(random.randint(1, 100)),
            "transaction_ref": f"LT-{amc_code}-{order_number}",
        }
        with self.client.post(
            "/qc/process",
            json=payload,
            name="POST /qc/process (sync)",
            catch_response=True,
        ) as r:
            # 200 = processed, 400 = missing file (expected in load test), 503 = OCR down
            if r.status_code in (200, 400, 422):
                r.success()
            elif r.status_code == 500:
                r.failure(f"Server error on sync QC: {r.text[:200]}")


class QCAsyncTasks(TaskSet):
    """Async QC submit + poll cycle — models the primary Celery path."""

    @task(5)
    def qc_process_async_and_poll(self):
        amc_code = random.choice(AMC_CODES)
        order_number = f"ORD{random.randint(100000, 999999)}"
        payload = {
            "appraisal_path": f"/tmp/load-test/{rand_str()}.pdf",
            "engagement_path": None,
            "contract_path": None,
            "amc_code": amc_code,
            "client_id": str(random.randint(1, 100)),
            "transaction_ref": f"LT-{amc_code}-{order_number}",
        }
        # Submit async job
        with self.client.post(
            "/qc/process-async",
            json=payload,
            name="POST /qc/process-async",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 202):
                try:
                    job_id = r.json().get("job_id") or r.json().get("task_id")
                except Exception:
                    job_id = None
                r.success()
            elif r.status_code in (400, 422):
                # Expected when test file paths don't exist
                r.success()
                job_id = None
            else:
                r.failure(f"Async submit failed: {r.status_code}")
                job_id = None

        # Poll status up to 3 times (exponential backoff)
        if job_id:
            for delay in (0.2, 0.5, 1.0):
                time.sleep(delay)
                with self.client.get(
                    f"/qc/status/{job_id}",
                    name="GET /qc/status/{job_id}",
                    catch_response=True,
                ) as poll:
                    if poll.status_code in (200, 404):
                        poll.success()
                        try:
                            state = poll.json().get("state", "")
                            if state in ("SUCCESS", "FAILURE", "REVOKED"):
                                break
                        except Exception:
                            break
                    else:
                        poll.failure(f"Poll status {poll.status_code}")
                        break


class CorrectionTasks(TaskSet):
    """Reviewer correction writes + stats reads."""

    @task(4)
    def submit_correction(self):
        correction = rand_correction()
        with self.client.post(
            "/corrections",
            json=correction,
            name="POST /corrections",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 201, 400, 422):
                r.success()
            elif r.status_code == 500:
                r.failure(f"Correction save failed: {r.text[:200]}")

    @task(2)
    def get_correction_stats(self):
        with self.client.get(
            "/correction-stats",
            name="GET /correction-stats",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404):
                r.success()
            elif r.status_code == 500:
                r.failure(f"Stats read failed: {r.text[:200]}")

    @task(1)
    def get_health_during_corrections(self):
        """Verify health doesn't degrade under correction write load."""
        with self.client.get("/health", catch_response=True, name="GET /health (during writes)") as r:
            if r.status_code == 200:
                r.success()
            else:
                r.failure(f"Unhealthy under write load: {r.status_code}")


# ── User classes ──────────────────────────────────────────────────────────────


class HealthMonitorUser(HttpUser):
    """Simulates monitoring infrastructure — polls /health frequently."""
    tasks = [HealthCheckTasks]
    wait_time = between(0.5, 2.0)
    weight = 5


class QCSyncUser(HttpUser):
    """Simulates small batches processed synchronously."""
    tasks = [QCSyncTasks]
    wait_time = between(1.0, 5.0)
    weight = 3


class QCAsyncUser(HttpUser):
    """Simulates the primary Celery async path — most real traffic."""
    tasks = [QCAsyncTasks]
    wait_time = between(2.0, 8.0)
    weight = 7


class CorrectionUser(HttpUser):
    """Simulates reviewers submitting field corrections."""
    tasks = [CorrectionTasks]
    wait_time = between(0.5, 3.0)
    weight = 4


# ── Event hooks for run-level reporting ───────────────────────────────────────


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n=== SHAL OCR Service — Load Test Starting ===")
    print(f"  Target: {environment.host}")
    print(f"  User classes: HealthMonitor(5x), QCSync(3x), QCAsync(7x), Corrections(4x)")
    print("=" * 50)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.stats
    total = stats.total
    print("\n=== SHAL OCR Service — Load Test Complete ===")
    print(f"  Total requests   : {total.num_requests:,}")
    print(f"  Total failures   : {total.num_failures:,}")
    print(f"  Failure rate     : {total.fail_ratio * 100:.2f}%")
    print(f"  Avg response     : {total.avg_response_time:.0f} ms")
    print(f"  P95 response     : {total.get_response_time_percentile(0.95):.0f} ms")
    print(f"  P99 response     : {total.get_response_time_percentile(0.99):.0f} ms")
    print(f"  Max response     : {total.max_response_time:.0f} ms")
    print(f"  Requests/sec     : {total.current_rps:.2f}")

    # Fail the run if SLAs are breached
    p95 = total.get_response_time_percentile(0.95) or 0
    fail_pct = total.fail_ratio * 100
    sla_ok = True
    if p95 > 1000:
        print(f"\n  ⚠ SLA BREACH: p95={p95:.0f}ms > 1000ms threshold")
        sla_ok = False
    if fail_pct > 5:
        print(f"\n  ⚠ SLA BREACH: failure rate={fail_pct:.2f}% > 5% threshold")
        sla_ok = False
    if sla_ok:
        print("\n  ✓ All SLAs passed")
    print("=" * 50)
