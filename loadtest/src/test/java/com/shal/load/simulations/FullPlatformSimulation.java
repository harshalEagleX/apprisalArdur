package com.shal.load.simulations;

import io.gatling.javaapi.core.*;
import io.gatling.javaapi.http.*;

import java.time.Duration;
import java.util.*;
import java.util.stream.Stream;

import static io.gatling.javaapi.core.CoreDsl.*;
import static io.gatling.javaapi.http.HttpDsl.*;

/**
 * Full-platform load simulation — 5,000 concurrent users across all 29 functional areas.
 *
 * Covers every API surface:
 *   Auth flow, Dashboard, Batch CRUD, QC status & results,
 *   Reviewer workflow, Analytics (all 6 endpoints), Audit trail,
 *   User management, Client management, Transaction management,
 *   Corrections proxy, System health, Override queue.
 *
 * Run:
 *   mvn gatling:test -pl loadtest -Dgatling.simulationClass=com.shal.load.simulations.FullPlatformSimulation
 *
 * Scale via:
 *   -Dloadtest.users=5000 -Dloadtest.rampSeconds=60 -Dloadtest.holdSeconds=300
 *   -Dloadtest.baseUrl=http://your-server:8080
 *   -Dloadtest.adminUser=admin -Dloadtest.adminPass=changeme
 */
public class FullPlatformSimulation extends Simulation {

    // ── Configuration ─────────────────────────────────────────────────────────

    private static final String BASE_URL =
        System.getProperty("loadtest.baseUrl", "http://localhost:8080");
    private static final int USERS =
        Integer.parseInt(System.getProperty("loadtest.users", "5000"));
    private static final int RAMP_SECONDS =
        Integer.parseInt(System.getProperty("loadtest.rampSeconds", "60"));
    private static final int HOLD_SECONDS =
        Integer.parseInt(System.getProperty("loadtest.holdSeconds", "300"));
    private static final String ADMIN_USER =
        System.getProperty("loadtest.adminUser", "admin");
    private static final String ADMIN_PASS =
        System.getProperty("loadtest.adminPass", "admin123");

    // ── HTTP protocol ─────────────────────────────────────────────────────────

    private final HttpProtocolBuilder httpProtocol = http
        .baseUrl(BASE_URL)
        .acceptHeader("application/json")
        .contentTypeHeader("application/json")
        .acceptEncodingHeader("gzip, deflate")
        .userAgentHeader("Gatling-LoadTest/3.10")
        .maxConnectionsPerHost(50)
        .shareConnections();

    // ── Shared auth chain — reused inside every scenario ──────────────────────

    private final ChainBuilder loginChain = exec(
        http("POST /api/auth/authenticate")
            .post("/api/auth/authenticate")
            .body(StringBody(
                "{\"username\":\"" + ADMIN_USER + "\",\"password\":\"" + ADMIN_PASS + "\"}"))
            .check(status().in(200, 401))
            .check(jsonPath("$.token").optional().saveAs("jwt"))
    );

    // ── Feeders ───────────────────────────────────────────────────────────────

    // Rotate through a pool of 1–1000 as synthetic batch IDs for read endpoints.
    // In a live-seeded environment (DocumentVolumeSimulation ran first) these exist.
    private final Iterator<Map<String, Object>> batchIdFeeder =
        Stream.iterate(1L, n -> (n % 1000) + 1)
              .map(n -> Collections.<String, Object>singletonMap("batchId", n))
              .iterator();

    private final Iterator<Map<String, Object>> qcResultIdFeeder =
        Stream.iterate(1L, n -> (n % 1000) + 1)
              .map(n -> Collections.<String, Object>singletonMap("qcResultId", n))
              .iterator();

    private final Iterator<Map<String, Object>> userIdFeeder =
        Stream.iterate(1L, n -> (n % 50) + 1)
              .map(n -> Collections.<String, Object>singletonMap("userId", n))
              .iterator();

    private final Iterator<Map<String, Object>> txIdFeeder =
        Stream.iterate(1L, n -> (n % 500) + 1)
              .map(n -> Collections.<String, Object>singletonMap("txId", n))
              .iterator();

    // ── Helper: auth header from session ─────────────────────────────────────

    private static String bearer(Session s) {
        return "Bearer " + s.getString("jwt");
    }

    // ── Scenario: Admin dashboard read path ───────────────────────────────────

    private final ScenarioBuilder adminDashboard = scenario("Admin — Dashboard & overview reads")
        .exec(loginChain)
        .pause(Duration.ofMillis(500))
        .exec(
            http("GET /api/admin/dashboard")
                .get("/api/admin/dashboard")
                .header("Authorization", session -> bearer(session))
                .check(status().in(200, 403))
        )
        .pause(Duration.ofMillis(200))
        .exec(
            http("GET /api/admin/system/health")
                .get("/api/admin/system/health")
                .header("Authorization", session -> bearer(session))
                .check(status().in(200, 403))
        )
        .exec(
            http("GET /api/me")
                .get("/api/me")
                .header("Authorization", session -> bearer(session))
                .check(status().in(200, 401))
        )
        .pause(Duration.ofMillis(300))
        .exec(
            http("GET /api/admin/clients")
                .get("/api/admin/clients")
                .header("Authorization", session -> bearer(session))
                .check(status().in(200, 403))
        )
        .exec(
            http("GET /api/admin/clients/stats")
                .get("/api/admin/clients/stats")
                .header("Authorization", session -> bearer(session))
                .check(status().in(200, 403))
        )
        .exec(
            http("GET /api/admin/users")
                .get("/api/admin/users")
                .header("Authorization", session -> bearer(session))
                .check(status().in(200, 403))
        );

    // ── Scenario: Batch reads (list + detail + status + QC) ──────────────────

    private final ScenarioBuilder batchReads = scenario("Batch — List, detail, status, QC results")
        .exec(loginChain)
        .pause(Duration.ofMillis(300))
        .repeat(10).on(
            feed(batchIdFeeder)
            .exec(
                http("GET /api/admin/batches")
                    .get("/api/admin/batches?page=0&size=20&sort=id,desc")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 400, 403))
            )
            .pause(Duration.ofMillis(100))
            .exec(
                http("GET /api/admin/batches/{batchId}")
                    .get("/api/admin/batches/#{batchId}")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .exec(
                http("GET /api/admin/batches/{batchId}/status")
                    .get("/api/admin/batches/#{batchId}/status")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .exec(
                http("GET /api/qc/results/{batchId}")
                    .get("/api/qc/results/#{batchId}")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .exec(
                http("GET /api/qc/progress/{batchId}")
                    .get("/api/qc/progress/#{batchId}")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .exec(
                http("GET /api/admin/batches/{batchId}/audit")
                    .get("/api/admin/batches/#{batchId}/audit")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .exec(
                http("GET /api/qc/findings/{batchId}")
                    .get("/api/qc/findings/#{batchId}")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .pause(Duration.ofMillis(150))
        );

    // ── Scenario: QC health + rules (read-only, no auth or admin-only) ────────

    private final ScenarioBuilder qcHealthAndRules = scenario("QC — Health & rules read")
        .exec(loginChain)
        .pause(Duration.ofMillis(100))
        .repeat(20).on(
            exec(
                http("GET /api/qc/health")
                    .get("/api/qc/health")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 503))
            )
            .pause(Duration.ofMillis(200))
            .exec(
                http("GET /api/qc/rules")
                    .get("/api/qc/rules")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .pause(Duration.ofMillis(300))
        );

    // ── Scenario: Reviewer workflow reads ─────────────────────────────────────

    private final ScenarioBuilder reviewerWorkflow = scenario("Reviewer — Queue + result reads")
        .exec(loginChain)
        .pause(Duration.ofMillis(400))
        .repeat(8).on(
            feed(qcResultIdFeeder)
            .exec(
                http("GET /api/reviewer/qc/results/pending")
                    .get("/api/reviewer/qc/results/pending")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .exec(
                http("GET /api/reviewer/qc/results/submitted")
                    .get("/api/reviewer/qc/results/submitted")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .pause(Duration.ofMillis(200))
            .exec(
                http("GET /api/reviewer/qc/{qcResultId}/result")
                    .get("/api/reviewer/qc/#{qcResultId}/result")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .exec(
                http("GET /api/reviewer/qc/{qcResultId}/rules")
                    .get("/api/reviewer/qc/#{qcResultId}/rules")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .exec(
                http("GET /api/reviewer/qc/{qcResultId}/progress")
                    .get("/api/reviewer/qc/#{qcResultId}/progress")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .exec(
                http("GET /api/reviewer/qc/{qcResultId}/audit")
                    .get("/api/reviewer/qc/#{qcResultId}/audit")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .exec(
                http("GET /api/reviewer/config")
                    .get("/api/reviewer/config")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .pause(Duration.ofMillis(250))
        );

    // ── Scenario: Analytics — all 6 endpoints ─────────────────────────────────

    private final ScenarioBuilder analytics = scenario("Analytics — All 6 endpoints")
        .exec(loginChain)
        .pause(Duration.ofMillis(300))
        .repeat(15).on(
            exec(
                http("GET /api/analytics/overview")
                    .get("/api/analytics/overview")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .exec(
                http("GET /api/analytics/ocr")
                    .get("/api/analytics/ocr")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .exec(
                http("GET /api/analytics/ml")
                    .get("/api/analytics/ml")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .exec(
                http("GET /api/analytics/operators")
                    .get("/api/analytics/operators")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .exec(
                http("GET /api/analytics/trend")
                    .get("/api/analytics/trend")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .exec(
                http("GET /api/analytics/review-sla")
                    .get("/api/analytics/review-sla")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .exec(
                http("GET /api/analytics/anomalies")
                    .get("/api/analytics/anomalies")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .pause(Duration.ofMillis(500))
        );

    // ── Scenario: Transaction API ─────────────────────────────────────────────

    private final ScenarioBuilder transactionReads = scenario("Transactions — List + detail + stats")
        .exec(loginChain)
        .pause(Duration.ofMillis(200))
        .repeat(12).on(
            feed(txIdFeeder)
            .exec(
                http("GET /api/admin/transactions/stats")
                    .get("/api/admin/transactions/stats")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .exec(
                http("GET /api/admin/transactions")
                    .get("/api/admin/transactions?page=0&size=20")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .exec(
                http("GET /api/admin/transactions/{id}")
                    .get("/api/admin/transactions/#{txId}")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .pause(Duration.ofMillis(200))
        );

    // ── Scenario: Override queue ───────────────────────────────────────────────

    private final ScenarioBuilder overrideQueue = scenario("Overrides — pending queue")
        .exec(loginChain)
        .pause(Duration.ofMillis(300))
        .repeat(20).on(
            exec(
                http("GET /api/reviewer/admin/overrides/pending")
                    .get("/api/reviewer/admin/overrides/pending")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .pause(Duration.ofMillis(400))
        );

    // ── Scenario: Auth + logout churn ─────────────────────────────────────────

    private final ScenarioBuilder authChurn = scenario("Auth — Login / logout cycle")
        .repeat(5).on(
            exec(
                http("POST /api/auth/authenticate")
                    .post("/api/auth/authenticate")
                    .body(StringBody(
                        "{\"username\":\"" + ADMIN_USER + "\",\"password\":\"" + ADMIN_PASS + "\"}"))
                    .check(status().in(200, 401, 429))
                    .check(jsonPath("$.token").optional().saveAs("jwt"))
            )
            .pause(Duration.ofSeconds(1))
            .doIf(s -> s.contains("jwt")).then(
                exec(
                    http("POST /api/auth/logout")
                        .post("/api/auth/logout")
                        .header("Authorization", session -> bearer(session))
                        .check(status().in(200, 204, 401))
                )
            )
            .pause(Duration.ofMillis(500))
        );

    // ── Scenario: QC file history reads ───────────────────────────────────────

    private final ScenarioBuilder qcHistory = scenario("QC — File history & diff reads")
        .exec(loginChain)
        .pause(Duration.ofMillis(300))
        .repeat(10).on(
            feed(qcResultIdFeeder)
            .exec(
                http("GET /api/qc/history/diff/{qcResultId}")
                    .get("/api/qc/history/diff/#{qcResultId}")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .exec(
                http("GET /api/qc/file/{qcResultId}")
                    .get("/api/qc/file/#{qcResultId}")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .pause(Duration.ofMillis(200))
        );

    // ── Scenario: Audit graph endpoints ───────────────────────────────────────

    private final ScenarioBuilder auditGraph = scenario("Audit — Graph endpoints")
        .exec(loginChain)
        .pause(Duration.ofMillis(400))
        .repeat(8).on(
            feed(batchIdFeeder)
            .exec(
                http("GET /api/audit/overview")
                    .get("/api/audit/overview")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 403))
            )
            .exec(
                http("GET /api/audit/batch/{batchId}")
                    .get("/api/audit/batch/#{batchId}")
                    .header("Authorization", session -> bearer(session))
                    .check(status().in(200, 404, 403))
            )
            .pause(Duration.ofMillis(300))
        );

    // ── Population distribution (mimics real user mix) ────────────────────────

    private static int pct(int totalUsers, int percent) {
        return Math.max(1, totalUsers * percent / 100);
    }

    {
        Duration ramp = Duration.ofSeconds(RAMP_SECONDS);
        Duration hold = Duration.ofSeconds(HOLD_SECONDS);
        // ramp-then-hold: inject N users over rampDuration, then hold rate for holdDuration
        // Gatling: pass multiple InjectionStep to the same injectOpen() call for sequencing.

        setUp(
            adminDashboard.injectOpen(
                rampUsers(pct(USERS, 20)).during(ramp),
                constantUsersPerSec(Math.max(1.0, pct(USERS, 20) / 60.0)).during(hold)),

            batchReads.injectOpen(
                rampUsers(pct(USERS, 25)).during(ramp),
                constantUsersPerSec(Math.max(1.0, pct(USERS, 25) / 60.0)).during(hold)),

            reviewerWorkflow.injectOpen(
                rampUsers(pct(USERS, 15)).during(ramp),
                constantUsersPerSec(Math.max(1.0, pct(USERS, 15) / 60.0)).during(hold)),

            analytics.injectOpen(
                rampUsers(pct(USERS, 10)).during(ramp),
                constantUsersPerSec(Math.max(1.0, pct(USERS, 10) / 60.0)).during(hold)),

            transactionReads.injectOpen(
                rampUsers(pct(USERS, 10)).during(ramp),
                constantUsersPerSec(Math.max(1.0, pct(USERS, 10) / 60.0)).during(hold)),

            qcHealthAndRules.injectOpen(
                rampUsers(pct(USERS, 8)).during(ramp),
                constantUsersPerSec(Math.max(1.0, pct(USERS, 8) / 60.0)).during(hold)),

            qcHistory.injectOpen(
                rampUsers(pct(USERS, 5)).during(ramp),
                constantUsersPerSec(Math.max(1.0, pct(USERS, 5) / 60.0)).during(hold)),

            auditGraph.injectOpen(
                rampUsers(pct(USERS, 4)).during(ramp),
                constantUsersPerSec(Math.max(1.0, pct(USERS, 4) / 60.0)).during(hold)),

            overrideQueue.injectOpen(
                rampUsers(pct(USERS, 2)).during(ramp),
                constantUsersPerSec(Math.max(1.0, pct(USERS, 2) / 60.0)).during(hold)),

            authChurn.injectOpen(
                rampUsers(pct(USERS, 1)).during(ramp))
        )
        .protocols(httpProtocol)
        .assertions(
            global().responseTime().percentile(95).lt(500),
            global().responseTime().percentile(99).lt(2000),
            global().failedRequests().percent().lt(5.0),
            global().requestsPerSec().gt(100.0)
        );
    }
}
