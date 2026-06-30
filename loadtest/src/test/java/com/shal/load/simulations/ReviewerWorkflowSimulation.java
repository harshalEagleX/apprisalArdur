package com.shal.load.simulations;

import com.shal.load.data.SyntheticData;
import io.gatling.javaapi.core.*;
import io.gatling.javaapi.http.*;

import java.time.Duration;
import java.util.*;
import java.util.stream.Stream;

import static io.gatling.javaapi.core.CoreDsl.*;
import static io.gatling.javaapi.http.HttpDsl.*;

/**
 * Reviewer Workflow Simulation — concurrent reviewer sessions under load.
 *
 * Models the complete reviewer day:
 *   Login → Queue check → Session start → Rules fetch → Decision saves → Sign-off
 *
 * Also covers:
 *   - Session heartbeats (keep-alive)
 *   - Override requests
 *   - Re-review requests
 *   - Corrections submission
 *   - QC file history reads (diff view)
 *
 * Run:
 *   mvn gatling:test -pl loadtest \
 *     -Dgatling.simulationClass=com.shal.load.simulations.ReviewerWorkflowSimulation \
 *     -Dloadtest.users=200 -Dloadtest.holdSeconds=180
 */
public class ReviewerWorkflowSimulation extends Simulation {

    private static final String BASE_URL =
        System.getProperty("loadtest.baseUrl", "http://localhost:8080");
    private static final int USERS =
        Integer.parseInt(System.getProperty("loadtest.users", "200"));
    private static final int HOLD_SECONDS =
        Integer.parseInt(System.getProperty("loadtest.holdSeconds", "180"));
    private static final String ADMIN_USER =
        System.getProperty("loadtest.adminUser", "admin");
    private static final String ADMIN_PASS =
        System.getProperty("loadtest.adminPass", "admin123");

    private final HttpProtocolBuilder httpProtocol = http
        .baseUrl(BASE_URL)
        .acceptHeader("application/json")
        .contentTypeHeader("application/json")
        .maxConnectionsPerHost(50)
        .shareConnections();

    // Pool of QC result IDs to use (assumes some QC results exist in the DB)
    private final Iterator<Map<String, Object>> qcResultIdFeeder =
        Stream.iterate(1L, n -> (n % 100) + 1)
              .map(n -> {
                  Map<String, Object> m = new LinkedHashMap<>();
                  m.put("qcResultId", n);
                  m.put("ruleResultId", n * 5);
                  return m;
              }).iterator();

    // ── Core reviewer day cycle ────────────────────────────────────────────────

    private final ScenarioBuilder reviewerDay = scenario("Reviewer — Full day workflow")
        // 1. Login
        .exec(
            http("POST /api/auth/authenticate")
                .post("/api/auth/authenticate")
                .body(StringBody(SyntheticData.authBody(ADMIN_USER, ADMIN_PASS)))
                .check(status().in(200, 401))
                .check(jsonPath("$.token").optional().saveAs("jwt"))
        )
        .pause(Duration.ofMillis(500))
        // 2. Check reviewer config
        .exec(
            http("GET /api/reviewer/config")
                .get("/api/reviewer/config")
                .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                .check(status().in(200, 401, 403))
        )
        // 3. Check pending queue
        .exec(
            http("GET /api/reviewer/qc/results/pending")
                .get("/api/reviewer/qc/results/pending")
                .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                .check(status().in(200, 401, 403))
        )
        .pause(Duration.ofSeconds(1))
        // Repeat the review cycle N times (mimics a full day of reviewing)
        .repeat(5).on(
            feed(qcResultIdFeeder)
            // 4. Open QC result
            .exec(
                http("GET /api/reviewer/qc/{qcResultId}/result")
                    .get("/api/reviewer/qc/#{qcResultId}/result")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .check(status().in(200, 404, 401, 403))
            )
            // 5. Start review session
            .exec(
                http("POST /api/reviewer/qc/{qcResultId}/session/start")
                    .post("/api/reviewer/qc/#{qcResultId}/session/start")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .body(StringBody("{}"))
                    .check(status().in(200, 409, 404, 401, 403))
                    .check(jsonPath("$.token").optional().saveAs("sessionToken"))
            )
            .pause(Duration.ofSeconds(2))
            // 6. Fetch all rules
            .exec(
                http("GET /api/reviewer/qc/{qcResultId}/rules")
                    .get("/api/reviewer/qc/#{qcResultId}/rules")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .check(status().in(200, 404, 401, 403))
            )
            // 7. Heartbeat (keep session alive)
            .exec(
                http("POST /api/reviewer/qc/{qcResultId}/session/heartbeat")
                    .post("/api/reviewer/qc/#{qcResultId}/session/heartbeat")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .body(StringBody(session -> {
                        String tok = session.getString("sessionToken");
                        return "{\"token\":\"" + (tok != null ? tok : "no-token") + "\"}";
                    }))
                    .check(status().in(200, 404, 401, 403, 409))
            )
            .pause(Duration.ofSeconds(1))
            // 8. Save decisions (simulate 3 rule decisions per file)
            .repeat(3).on(
                exec(
                    http("POST /api/reviewer/decision/save")
                        .post("/api/reviewer/decision/save")
                        .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                        .body(StringBody(session -> {
                            long ruleId = ((Number) session.get("ruleResultId")).longValue();
                            String decision = Math.random() > 0.2 ? "PASS" : "FAIL";
                            return SyntheticData.saveDecisionBody(ruleId, decision);
                        }))
                        .check(status().in(200, 400, 404, 401, 403, 409))
                )
                .pause(Duration.ofMillis(300))
            )
            // 9. Check progress
            .exec(
                http("GET /api/reviewer/qc/{qcResultId}/progress")
                    .get("/api/reviewer/qc/#{qcResultId}/progress")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .check(status().in(200, 404, 401, 403))
            )
            // 10. Sign off (submit review)
            .exec(
                http("POST /api/reviewer/qc/{qcResultId}/submit")
                    .post("/api/reviewer/qc/#{qcResultId}/submit")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .body(StringBody(session -> {
                        String tok = session.getString("sessionToken");
                        String outcome = Math.random() > 0.1 ? "PASS" : "FAIL";
                        return "{\"sessionToken\":\"" + (tok != null ? tok : "none")
                            + "\",\"finalDecision\":\"" + outcome + "\"}";
                    }))
                    .check(status().in(200, 400, 404, 401, 403, 409))
            )
            // 11. View submitted queue
            .exec(
                http("GET /api/reviewer/qc/results/submitted")
                    .get("/api/reviewer/qc/results/submitted")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .check(status().in(200, 401, 403))
            )
            .pause(Duration.ofMillis(500))
        );

    // ── Corrections write scenario ─────────────────────────────────────────────

    private final ScenarioBuilder correctionSubmitter = scenario("Reviewer — Corrections stream")
        .exec(
            http("POST /api/auth/authenticate")
                .post("/api/auth/authenticate")
                .body(StringBody(SyntheticData.authBody(ADMIN_USER, ADMIN_PASS)))
                .check(status().in(200, 401))
                .check(jsonPath("$.token").optional().saveAs("jwt"))
        )
        .during(Duration.ofSeconds(HOLD_SECONDS)).on(
            exec(
                http("POST /api/reviewer/corrections")
                    .post("/api/reviewer/corrections")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .body(StringBody(session ->
                        SyntheticData.correctionBody(
                            SyntheticData.randomFieldName(),
                            SyntheticData.randomValue(),
                            SyntheticData.randomValue()
                        )
                    ))
                    .check(status().in(200, 201, 400, 401, 403))
            )
            .pause(Duration.ofMillis(200))
        );

    // ── Override request scenario ──────────────────────────────────────────────

    private final ScenarioBuilder overrideChecks = scenario("Admin — Override queue polling")
        .exec(
            http("POST /api/auth/authenticate")
                .post("/api/auth/authenticate")
                .body(StringBody(SyntheticData.authBody(ADMIN_USER, ADMIN_PASS)))
                .check(status().in(200, 401))
                .check(jsonPath("$.token").optional().saveAs("jwt"))
        )
        .during(Duration.ofSeconds(HOLD_SECONDS)).on(
            exec(
                http("GET /api/reviewer/admin/overrides/pending")
                    .get("/api/reviewer/admin/overrides/pending")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .check(status().in(200, 401, 403))
            )
            .pause(Duration.ofSeconds(2))
        );

    {
        Duration ramp = Duration.ofSeconds(30);
        Duration hold = Duration.ofSeconds(HOLD_SECONDS);

        setUp(
            reviewerDay.injectOpen(
                rampUsers((int)(USERS * 0.80)).during(ramp),
                constantUsersPerSec(Math.max(1.0, (USERS * 0.80) / 60.0)).during(hold)),

            correctionSubmitter.injectOpen(
                rampUsers(Math.max(1, (int)(USERS * 0.15))).during(ramp)),

            overrideChecks.injectOpen(
                rampUsers(Math.max(1, (int)(USERS * 0.05))).during(ramp))
        )
        .protocols(httpProtocol)
        .assertions(
            global().responseTime().percentile(95).lt(800),
            global().responseTime().percentile(99).lt(2000),
            global().failedRequests().percent().lt(10.0),
            details("GET /api/reviewer/qc/results/pending")
                .responseTime().percentile(99).lt(500)
        );
    }
}
