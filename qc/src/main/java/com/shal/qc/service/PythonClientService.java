package com.shal.qc.service;

import com.shal.qc.config.OcrServiceConfig;
import com.shal.common.dto.shalqc.ShalqcResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;

import java.nio.file.Path;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

/**
 * Client for the SHALqc service. The single live QC path is the synchronous
 * {@link #processQCShalqc} → native {@link ShalqcResponse} (Approach B); the
 * retired ocr-service Celery/rule-engine flow (submit/poll/process-legacy) was
 * removed 2026-07-15. Also proxies reviewer corrections and exposes health/rules.
 */
@Service
public class PythonClientService {

    private static final Logger log = LoggerFactory.getLogger(PythonClientService.class);

    private final RestTemplate restTemplate;          // short-timeout: health/progress/rules/corrections
    private final RestTemplate processRestTemplate;   // long-timeout: synchronous /qc/process only (QL-8)
    private final OcrServiceConfig config;
    private final ThreadLocal<Integer> lastRetryCount = ThreadLocal.withInitial(() -> 0);

    public PythonClientService(RestTemplate restTemplate,
                               @Qualifier("pythonProcessRestTemplate") RestTemplate processRestTemplate,
                               OcrServiceConfig config) {
        this.restTemplate = restTemplate;
        this.processRestTemplate = processRestTemplate;
        this.config = config;
    }

    public record PythonProgress(String stage, String message, double subPercent, long elapsedMs) { }

    public int getLastRetryCount() { return lastRetryCount.get(); }

    /**
     * SHALqc (Approach B) synchronous path: POST the multipart order to the SHALqc
     * service's {@code /qc/process} and deserialize its native OrderQCResponse
     * ({@link ShalqcResponse}) — cards + coordinates + llm_interactions. Bounded
     * retry; a 4xx (bad input) is not retried. The optional stage callback streams
     * sub-progress via a background poller on {@code /qc/progress/{token}}.
     */
    public ShalqcResponse processQCShalqc(Path appraisalPath, Path xmlPath,
                                          Path engagementPath, Path contractPath,
                                          QCModelConfig modelConfig, Consumer<PythonProgress> stageCallback,
                                          Long batchId, Long batchFileId, Long qcResultId, String sourceHash,
                                          String engagementStatus, String clientId, String amcCode) {
        String url = config.getUrl() + "/qc/process";
        QCModelConfig safeModelConfig = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        String progressToken = UUID.randomUUID().toString();
        lastRetryCount.set(0);

        if (!appraisalPath.toFile().exists()) {
            throw new RuntimeException("Appraisal PDF not found on disk: " + appraisalPath);
        }

        MultiValueMap<String, Object> body =
                buildShalqcBody(appraisalPath, xmlPath, engagementPath, contractPath, engagementStatus, amcCode);
        body.add("progress_token", progressToken);
        String correlationId = appendProcessingContext(body, batchId, batchFileId, qcResultId, sourceHash, safeModelConfig, clientId);
        log.info("Calling SHALqc /qc/process: {} appraisal={} xml={} engagement={} contract={}",
                url, appraisalPath.getFileName(),
                xmlPath != null ? xmlPath.getFileName() : "none",
                engagementPath != null ? engagementPath.getFileName() : "none",
                contractPath != null ? contractPath.getFileName() : "none");

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        headers.set("X-Correlation-ID", correlationId);
        if (config.getApiKey() != null && !config.getApiKey().isBlank()) {
            headers.set("X-API-Key", config.getApiKey());
        }
        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

        AtomicBoolean stopPoller = new AtomicBoolean(false);
        if (stageCallback != null) {
            Thread poller = new Thread(() -> pollSubProgress(progressToken, stageCallback, stopPoller),
                    "qc-shalqc-progress-" + progressToken.substring(0, 8));
            poller.setDaemon(true);
            poller.start();
        }

        int maxAttempts = Math.max(1, config.getRetryAttempts() + 1);
        try {
            RuntimeException last = null;
            for (int attempt = 1; attempt <= maxAttempts; attempt++) {
                try {
                    ResponseEntity<ShalqcResponse> response = processRestTemplate.exchange(
                            url, HttpMethod.POST, requestEntity, ShalqcResponse.class);
                    ShalqcResponse result = response.getBody();
                    if (result == null) {
                        throw new RuntimeException("SHALqc service returned empty response body");
                    }
                    lastRetryCount.set(Math.max(0, attempt - 1));
                    log.info("SHALqc QC completed: order={} cards={} summary={}",
                            result.orderId(),
                            result.cards() != null ? result.cards().size() : 0,
                            result.summary());
                    return result;
                } catch (org.springframework.web.client.HttpClientErrorException e) {
                    // 4xx = bad input (422 invalid PDF, 400 bad request); retrying won't help.
                    log.error("SHALqc service rejected request ({}): {}", e.getStatusCode(), e.getResponseBodyAsString());
                    throw new RuntimeException("SHALqc rejected request: " + e.getStatusCode(), e);
                } catch (RuntimeException e) {
                    last = e;
                    log.warn("SHALqc call attempt {}/{} failed: {}", attempt, maxAttempts, e.getMessage());
                }
            }
            throw last != null ? last : new RuntimeException("SHALqc call failed after " + maxAttempts + " attempts");
        } finally {
            stopPoller.set(true);
        }
    }

    /**
     * Poll Python /qc/progress/{token} every ~1.5s and forward each snapshot
     * to the stage callback. Runs on a dedicated daemon thread, exits as soon
     * as stop is signalled or the token returns 404 repeatedly.
     */
    private void pollSubProgress(String token, Consumer<PythonProgress> callback, AtomicBoolean stop) {
        String url = config.getUrl() + "/qc/progress/" + token;
        HttpHeaders headers = new HttpHeaders();
        if (config.getApiKey() != null && !config.getApiKey().isBlank()) {
            headers.set("X-API-Key", config.getApiKey());
        }
        HttpEntity<Void> entity = new HttpEntity<>(headers);

        int consecutive404 = 0;
        while (!stop.get() && !Thread.currentThread().isInterrupted()) {
            try {
                Thread.sleep(1500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            if (stop.get()) return;
            try {
                @SuppressWarnings("rawtypes")
                ResponseEntity<Map> resp = restTemplate.exchange(url, HttpMethod.GET, entity, Map.class);
                consecutive404 = 0;
                @SuppressWarnings("unchecked")
                Map<String, Object> body = resp.getBody();
                if (body == null) continue;
                String stage = stringFromMap(body, "stage");
                String message = stringFromMap(body, "message");
                Number subPercent = numberFromMap(body, "sub_percent");
                Number elapsedMs = numberFromMap(body, "elapsed_ms");
                callback.accept(new PythonProgress(
                        stage,
                        message,
                        subPercent != null ? subPercent.doubleValue() : 0.0,
                        elapsedMs != null ? elapsedMs.longValue() : 0L));
            } catch (org.springframework.web.client.HttpClientErrorException.NotFound nf) {
                // Token not registered yet (Python has not started writing) or
                // already evicted. Tolerate a few 404s, then give up.
                if (++consecutive404 >= 5) return;
            } catch (Exception e) {
                log.debug("progress poll for {} failed: {}", token, e.getMessage());
            }
        }
    }

    private static String stringFromMap(Map<String, Object> m, String k) {
        Object v = m.get(k);
        return v != null ? v.toString() : null;
    }

    private static Number numberFromMap(Map<String, Object> m, String k) {
        Object v = m.get(k);
        return v instanceof Number ? (Number) v : null;
    }

    /**
     * Proxy a reviewer field correction to Python's /corrections endpoint.
     * All corrections must flow through here (not directly to Python) so the Java
     * authorization layer is in the critical path for every reviewer write (VF-6).
     *
     * @return the raw JSON body from Python, or null on error
     */
    public String submitCorrection(Map<String, Object> correctionPayload) {
        try {
            String url = config.getUrl() + "/corrections";
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            if (config.getApiKey() != null && !config.getApiKey().isBlank()) {
                headers.set("X-API-Key", config.getApiKey());
            }
            ResponseEntity<String> response = restTemplate.exchange(
                    url, HttpMethod.POST, new HttpEntity<>(correctionPayload, headers), String.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("Python correction submit failed: {}", e.getMessage());
            throw new RuntimeException("Failed to submit correction to Python service: " + e.getMessage(), e);
        }
    }

    /**
     * SHALqc {@code /qc/process} Mode-A multipart body. Its file parts are named
     * {@code appraisal/xml/engagement/contract} (NOT the retired ocr-service
     * {@code file/xml_file/engagement_letter/contract_file} — that name drift is
     * exactly what a live run caught as a 400 "missing appraisal"). Only the
     * appraisal is required; the rest are optional.
     */
    private MultiValueMap<String, Object> buildShalqcBody(
            Path appraisalPath, Path xmlPath, Path engagementPath, Path contractPath,
            String engagementStatus, String amcCode) {
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        java.io.File appraisalFile = Objects.requireNonNull(appraisalPath).toFile();
        if (!appraisalFile.exists() || !appraisalFile.isFile()) {
            throw new RuntimeException("Appraisal PDF not found on disk (path: " + appraisalPath + ").");
        }
        body.add("appraisal", new FileSystemResource(appraisalFile));
        if (xmlPath != null && xmlPath.toFile().isFile())
            body.add("xml", new FileSystemResource(xmlPath.toFile()));
        if (engagementPath != null && engagementPath.toFile().isFile())
            body.add("engagement", new FileSystemResource(engagementPath.toFile()));
        if (contractPath != null && contractPath.toFile().isFile())
            body.add("contract", new FileSystemResource(contractPath.toFile()));
        body.add("use_llm", "true");
        if (engagementStatus != null && !engagementStatus.isBlank())
            body.add("engagement_status", engagementStatus);
        // The AMC/client code tells shalqc which compiled bundle to load. Without
        // it, shalqc can't resolve the AMC from a temp order dir and falls back to
        // the generic _base catalog (empty `expects`, filler bindings → mass VERIFY).
        if (amcCode != null && !amcCode.isBlank())
            body.add("amc_code", amcCode);
        return body;
    }

    private String appendProcessingContext(MultiValueMap<String, Object> body,
                                         Long batchId, Long batchFileId, Long qcResultId,
                                         String sourceHash, QCModelConfig cfg, String clientId) {
        String correlationId = org.slf4j.MDC.get("correlationId");
        if (correlationId == null || correlationId.isBlank()) {
            correlationId = batchId != null ? "batch:" + batchId : UUID.randomUUID().toString();
        }
        body.add("correlation_id", correlationId);
        if (batchId != null) body.add("batch_id", String.valueOf(batchId));
        if (batchFileId != null) body.add("batch_file_id", String.valueOf(batchFileId));
        if (qcResultId != null) body.add("qc_result_id", String.valueOf(qcResultId));
        if (clientId != null && !clientId.isBlank()) body.add("client_id", clientId);
        // Order (AppraisalTransaction) traceability — set via MDC by QCProcessingService
        // right before the Python call, same mechanism used for correlationId. Lets
        // Python's own audit tables be traced back to the Java Order.
        String orderRef = org.slf4j.MDC.get("orderRef");
        if (orderRef != null && !orderRef.isBlank()) {
            body.add("order_ref", orderRef);
        }
        if (sourceHash != null && !sourceHash.isBlank() && batchFileId != null) {
            body.add("idempotency_key", String.join("|",
                    String.valueOf(batchFileId),
                    sourceHash,
                    cfg.provider(),
                    cfg.textModel(),
                    cfg.visionModel(),
                    "rules:1.0"));
        }
        return correlationId;
    }

    /**
     * Check if the SHALqc service is healthy.
     */
    public boolean isHealthy() {
        try {
            // Use /live (instant, no DB checks) — /health is heavier
            String url = config.getUrl() + "/live";
            ResponseEntity<String> response = restTemplate.getForEntity(url, String.class);
            return response.getStatusCode().is2xxSuccessful();
        } catch (Exception e) {
            log.warn("Python service liveness check failed: {}", e.getMessage());
            return false;
        }
    }

    /**
     * Get the list of QC rules from the SHALqc service.
     */
    public String getRules() {
        try {
            String url = config.getUrl() + "/qc/rules";
            HttpHeaders headers = new HttpHeaders();
            if (config.getApiKey() != null && !config.getApiKey().isBlank()) {
                headers.set("X-API-Key", config.getApiKey());
            }
            ResponseEntity<String> response = restTemplate.exchange(
                    url, HttpMethod.GET, new HttpEntity<>(headers), String.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("Failed to get QC rules: {}", e.getMessage());
            return null;
        }
    }

    // ── AMC checklists (frontend-authored, per client and form version) ────────
    //
    // The checklist lives in SHALqc because that is what evaluates it. The
    // browser cannot reach SHALqc — it only ever talks to this service, and the
    // SHALqc API key must never leave the server — so these three methods are
    // the bridge that makes the checklist editable from the admin UI.
    //
    // The payload is passed through as an opaque String rather than mapped to a
    // DTO on purpose: 2.6 and 3.6 items do NOT share a schema (3.6 adds
    // polarity/proof/evidence_kind because its items are answered from page
    // images), and a version — or the UI — must be able to add a field without
    // a Java release. Mapping here would silently drop whatever Java had not
    // been taught about yet, which is the worst possible failure for a config
    // screen: the user saves, sees success, and their change is gone.

    private HttpHeaders shalqcHeaders(boolean json) {
        HttpHeaders headers = new HttpHeaders();
        if (config.getApiKey() != null && !config.getApiKey().isBlank()) {
            headers.set("X-API-Key", config.getApiKey());
        }
        if (json) {
            headers.setContentType(org.springframework.http.MediaType.APPLICATION_JSON);
        }
        return headers;
    }

    /** Every (client, form version) checklist SHALqc knows about. */
    public String listChecklists() {
        try {
            ResponseEntity<String> response = restTemplate.exchange(
                    config.getUrl() + "/checklists", HttpMethod.GET,
                    new HttpEntity<>(shalqcHeaders(false)), String.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("Failed to list checklists: {}", e.getMessage());
            return null;
        }
    }

    /** One client's checklist for one form version, as editable rows. */
    public String getChecklist(String amcCode, String uadVersion) {
        try {
            String url = config.getUrl() + "/checklists/" + amcCode + "/" + uadVersion;
            ResponseEntity<String> response = restTemplate.exchange(
                    url, HttpMethod.GET, new HttpEntity<>(shalqcHeaders(false)), String.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("Failed to get checklist {}/{}: {}", amcCode, uadVersion, e.getMessage());
            return null;
        }
    }

    /**
     * Save an edited checklist.
     *
     * SHALqc validates and answers 400 with a message written to be shown to the
     * operator ("duplicate rule_id 'X-1' — verdicts are keyed by it…"). That
     * message is propagated rather than swallowed: a config screen that reports
     * a generic failure leaves the user with no idea what to change.
     */
    public String saveChecklist(String amcCode, String uadVersion, String body) {
        String url = config.getUrl() + "/checklists/" + amcCode + "/" + uadVersion;
        ResponseEntity<String> response = restTemplate.exchange(
                url, HttpMethod.PUT, new HttpEntity<>(body, shalqcHeaders(true)), String.class);
        return response.getBody();
    }

    /** Fork the built-in catalogue into this client's own editable copy. */
    public String seedChecklist(String amcCode, String uadVersion) {
        String url = config.getUrl() + "/checklists/" + amcCode + "/" + uadVersion + "/seed";
        ResponseEntity<String> response = restTemplate.exchange(
                url, HttpMethod.POST, new HttpEntity<>(shalqcHeaders(true)), String.class);
        return response.getBody();
    }
}
