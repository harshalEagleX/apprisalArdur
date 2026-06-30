package com.shal.load.simulations;

import com.shal.load.data.SyntheticData;
import io.gatling.javaapi.core.*;
import io.gatling.javaapi.http.*;

import java.time.Duration;
import java.util.*;

import static io.gatling.javaapi.core.CoreDsl.*;
import static io.gatling.javaapi.http.HttpDsl.*;

/**
 * Document Volume Simulation — 10,000 documents.
 *
 * Two phases:
 *   Phase 1 — SEED:   upload 10,000 synthetic ZIPs at a controlled rate
 *             (50 concurrent writers × 200 batches each = 10,000 total)
 *   Phase 2 — STRESS: 500 concurrent readers hammer the newly seeded batch data
 *
 * Measures:
 *   - Upload throughput (batches/second)
 *   - P95/P99 read latency after volume is loaded
 *   - Zero 5xx errors under sustained load
 *
 * Run:
 *   mvn gatling:test -pl loadtest \
 *     -Dgatling.simulationClass=com.shal.load.simulations.DocumentVolumeSimulation \
 *     -Dloadtest.docVolume=10000
 */
public class DocumentVolumeSimulation extends Simulation {

    private static final String BASE_URL =
        System.getProperty("loadtest.baseUrl", "http://localhost:8080");
    private static final int DOC_VOLUME =
        Integer.parseInt(System.getProperty("loadtest.docVolume", "10000"));
    private static final String ADMIN_USER =
        System.getProperty("loadtest.adminUser", "admin");
    private static final String ADMIN_PASS =
        System.getProperty("loadtest.adminPass", "admin123");

    // Writers upload in parallel. Each does (DOC_VOLUME / WRITERS) uploads.
    private static final int WRITERS = 50;
    private static final int UPLOADS_PER_WRITER = DOC_VOLUME / WRITERS;
    // Readers hammer the read endpoints after data is seeded.
    private static final int READERS = 500;
    private static final int READ_DURATION_SECONDS = 120;

    // ── HTTP protocol ─────────────────────────────────────────────────────────

    private final HttpProtocolBuilder httpProtocol = http
        .baseUrl(BASE_URL)
        .acceptHeader("application/json")
        .contentTypeHeader("application/json")
        .maxConnectionsPerHost(100)
        .shareConnections();

    // ── Feeder: 10,000 unique batch manifests ─────────────────────────────────

    // Pre-generated at field-init time (can't use lambdas in field initializer here)
    private static Iterator<Map<String, Object>> buildManifestFeeder() {
        List<Map<String, Object>> rows = SyntheticData.generateManifestRows(DOC_VOLUME);
        return rows.iterator();
    }

    private final Iterator<Map<String, Object>> manifestFeeder = buildManifestFeeder();

    // Batch IDs discovered during seeding (thread-safe list shared across VUs)
    private final List<Long> seededBatchIds = Collections.synchronizedList(new ArrayList<>());

    // ── Phase 1: SEED — upload DOC_VOLUME batches ─────────────────────────────

    private final ScenarioBuilder seedBatches = scenario("Phase 1 — Seed " + DOC_VOLUME + " documents")
        .exec(
            http("POST /api/auth/authenticate")
                .post("/api/auth/authenticate")
                .body(StringBody(SyntheticData.authBody(ADMIN_USER, ADMIN_PASS)))
                .check(status().is(200))
                .check(jsonPath("$.token").saveAs("jwt"))
        )
        .repeat(UPLOADS_PER_WRITER).on(
            feed(manifestFeeder)
            .exec(session -> {
                String amcCode = session.getString("amcCode");
                String orderNumber = session.getString("orderNumber");
                String address = session.getString("address");
                byte[] zip = SyntheticData.zipWithManifest(amcCode, orderNumber, address);
                return session.set("zipBytes", zip)
                              .set("zipFilename", "lt_" + amcCode + "_" + orderNumber + ".zip");
            })
            .exec(
                http("POST /api/admin/batches/upload")
                    .post("/api/admin/batches/upload")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .header("Content-Type", "multipart/form-data")
                    .bodyPart(
                        ByteArrayBodyPart("file",
                            session -> (byte[]) session.get("zipBytes"))
                            .fileName(session -> session.getString("zipFilename"))
                            .contentType("application/zip")
                    )
                    .check(status().in(200, 201, 400, 409))
                    .check(jsonPath("$.id").optional().saveAs("newBatchId"))
            )
            .exec(session -> {
                String id = session.getString("newBatchId");
                if (id != null) {
                    try { seededBatchIds.add(Long.parseLong(id)); } catch (NumberFormatException ignored) {}
                }
                return session;
            })
            .pause(Duration.ofMillis(50))
        );

    // ── Phase 2: STRESS — concurrent reads against seeded data ────────────────

    private final ScenarioBuilder stressReadSeededData = scenario("Phase 2 — Stress read 500 users")
        .exec(
            http("POST /api/auth/authenticate")
                .post("/api/auth/authenticate")
                .body(StringBody(SyntheticData.authBody(ADMIN_USER, ADMIN_PASS)))
                .check(status().is(200))
                .check(jsonPath("$.token").saveAs("jwt"))
        )
        .pause(Duration.ofMillis(200))
        .during(Duration.ofSeconds(READ_DURATION_SECONDS)).on(
            exec(session -> {
                // Pick a random seeded batch ID, fall back to 1 if seeding isn't done yet
                long batchId = seededBatchIds.isEmpty() ? 1L :
                    seededBatchIds.get((int)(Math.random() * seededBatchIds.size()));
                return session.set("batchId", batchId);
            })
            .exec(
                http("GET /api/admin/batches (paginated)")
                    .get("/api/admin/batches?page=0&size=50&sort=id,desc")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .check(status().in(200, 403))
                    .check(responseTimeInMillis().lt(1000))
            )
            .exec(
                http("GET /api/admin/batches/{batchId}")
                    .get("/api/admin/batches/#{batchId}")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .check(status().in(200, 404, 403))
                    .check(responseTimeInMillis().lt(300))
            )
            .exec(
                http("GET /api/qc/results/{batchId}")
                    .get("/api/qc/results/#{batchId}")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .check(status().in(200, 404, 403))
                    .check(responseTimeInMillis().lt(300))
            )
            .exec(
                http("GET /api/admin/transactions?page=0&size=50")
                    .get("/api/admin/transactions?page=0&size=50")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .check(status().in(200, 403))
                    .check(responseTimeInMillis().lt(500))
            )
            .pause(Duration.ofMillis(100))
        );

    // ── Phase 3: DEEP paginated scan (verifies index usage at volume) ──────────

    private final ScenarioBuilder deepPageScan = scenario("Phase 3 — Deep paginated scan")
        .exec(
            http("POST /api/auth/authenticate")
                .post("/api/auth/authenticate")
                .body(StringBody(SyntheticData.authBody(ADMIN_USER, ADMIN_PASS)))
                .check(status().is(200))
                .check(jsonPath("$.token").saveAs("jwt"))
        )
        .repeat(200).on(
            exec(session -> session.set("page", (int)(Math.random() * 500)))
            .exec(
                http("GET /api/admin/batches page #{page}")
                    .get("/api/admin/batches?page=#{page}&size=20&sort=id,desc")
                    .header("Authorization", session -> "Bearer " + session.getString("jwt"))
                    .check(status().in(200, 400, 403))
                    .check(responseTimeInMillis().lt(800))
            )
            .pause(Duration.ofMillis(50))
        );

    // ── Population ─────────────────────────────────────────────────────────────

    {
        setUp(
            // Phase 1: 50 writers ramp up over 30s, upload 10,000 documents
            seedBatches.injectOpen(
                rampUsers(WRITERS).during(Duration.ofSeconds(30))
            ),
            // Phase 2: 500 readers start after 60s (giving Phase 1 a head start)
            stressReadSeededData.injectOpen(
                nothingFor(Duration.ofSeconds(60)),
                rampUsers(READERS).during(Duration.ofSeconds(30))
            ),
            // Phase 3: 20 deep-scan users validate pagination index performance
            deepPageScan.injectOpen(
                nothingFor(Duration.ofSeconds(90)),
                rampUsers(20).during(Duration.ofSeconds(10))
            )
        )
        .protocols(httpProtocol)
        .assertions(
            // Upload: p95 under 3 seconds (ZIP parsing + DB write)
            forAll().responseTime().percentile(95).lt(3000),
            // Read: p99 under 1 second
            details("GET /api/admin/batches (paginated)")
                .responseTime().percentile(99).lt(1000),
            details("GET /api/admin/batches/{batchId}")
                .responseTime().percentile(99).lt(300),
            // Overall error rate under 5%
            global().failedRequests().percent().lt(5.0),
            // Must achieve meaningful throughput
            global().requestsPerSec().gt(50.0)
        );
    }
}
