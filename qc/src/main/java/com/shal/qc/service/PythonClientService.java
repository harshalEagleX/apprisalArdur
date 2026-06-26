package com.shal.qc.service;

import com.shal.qc.config.OcrServiceConfig;
import com.shal.common.dto.python.PythonQCResponse;
import com.shal.common.util.TimelineLog;
import com.fasterxml.jackson.annotation.JsonProperty;
import tools.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Service for calling the Python OCR/QC service.
 * Handles HTTP communication with Python /qc/process endpoint.
 */
@Service
public class PythonClientService {

    private static final Logger log = LoggerFactory.getLogger(PythonClientService.class);

    private final RestTemplate restTemplate;          // short-timeout: health/submit/poll/rules/feedback
    private final RestTemplate processRestTemplate;   // long-timeout: synchronous /qc/process only (QL-8)
    private final OcrServiceConfig config;
    private final ObjectMapper objectMapper;
    private final ThreadLocal<Integer> lastRetryCount = ThreadLocal.withInitial(() -> 0);

    public PythonClientService(RestTemplate restTemplate,
                               @Qualifier("pythonProcessRestTemplate") RestTemplate processRestTemplate,
                               OcrServiceConfig config,
                               ObjectMapper objectMapper) {
        this.restTemplate = restTemplate;
        this.processRestTemplate = processRestTemplate;
        this.config = config;
        this.objectMapper = objectMapper;
    }

    /**
     * Process a document pair through Python QC pipeline.
     *
     * @param appraisalPath  Path to appraisal PDF (ACTUAL data)
     * @param engagementPath Path to engagement letter PDF (EXPECTED data), can be
     *                       null
     * @return QC processing results from Python
     */
    public PythonQCResponse processQC(Path appraisalPath, Path engagementPath) {
        return processQC(appraisalPath, engagementPath, null);
    }

    public PythonQCResponse processQC(Path appraisalPath, Path engagementPath, Path contractPath) {
        return processQC(appraisalPath, engagementPath, contractPath, QCModelConfig.defaults());
    }

    public PythonQCResponse processQC(Path appraisalPath, Path engagementPath, Path contractPath, QCModelConfig modelConfig) {
        return processQC(appraisalPath, engagementPath, contractPath, modelConfig, null);
    }

    public PythonQCResponse processQC(Path appraisalPath, Path engagementPath, Path contractPath,
                                      QCModelConfig modelConfig, Consumer<PythonProgress> stageCallback) {
        return processQC(appraisalPath, engagementPath, contractPath, modelConfig, stageCallback, null, null, null, null, null);
    }

    public PythonQCResponse processQC(Path appraisalPath, Path engagementPath, Path contractPath,
                                      QCModelConfig modelConfig, Consumer<PythonProgress> stageCallback,
                                      Long batchId, Long batchFileId, Long qcResultId, String sourceHash,
                                      String engagementStatus) {
        return processQC(appraisalPath, null, engagementPath, contractPath,
                modelConfig, stageCallback, batchId, batchFileId, qcResultId, sourceHash, engagementStatus);
    }

    public PythonQCResponse processQC(Path appraisalPath, Path xmlPath,
                                      Path engagementPath, Path contractPath,
                                      QCModelConfig modelConfig, Consumer<PythonProgress> stageCallback,
                                      Long batchId, Long batchFileId, Long qcResultId, String sourceHash,
                                      String engagementStatus) {
        String url = config.getUrl() + "/qc/process";
        long callStarted = System.nanoTime();
        QCModelConfig safeModelConfig = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        String progressToken = UUID.randomUUID().toString();
        lastRetryCount.set(0);

        log.info("Calling Python QC service: {} with appraisal: {}, xml: {}, engagement: {}, contract: {}, model: {}",
                url, appraisalPath.getFileName(),
                xmlPath != null ? xmlPath.getFileName() : "none",
                engagementPath != null ? engagementPath.getFileName() : "none",
                contractPath != null ? contractPath.getFileName() : "none",
                safeModelConfig.label());

        MultiValueMap<String, Object> body =
                buildBaseBody(appraisalPath, xmlPath, engagementPath, contractPath, engagementStatus, safeModelConfig);
        body.add("progress_token", progressToken);   // sync path streams progress
        String correlationId = appendProcessingContext(body, batchId, batchFileId, qcResultId, sourceHash, safeModelConfig);
        log.info(TimelineLog.event("admin_batches", "java_python_call_start",
                "batch_id", batchId,
                "batch_file_id", batchFileId,
                "correlation_id", correlationId,
                "progress_token", progressToken,
                "url", url,
                "appraisal", appraisalPath.getFileName(),
                "engagement", engagementPath != null ? engagementPath.getFileName() : "none",
                "contract", contractPath != null ? contractPath.getFileName() : "none",
                "model", safeModelConfig.label()));

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        headers.set("X-Correlation-ID", correlationId);
        // SECURITY: send API key to Python service
        if (config.getApiKey() != null && !config.getApiKey().isBlank()) {
            headers.set("X-API-Key", config.getApiKey());
        }

        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

        // Background poller — pulls sub-stage updates from Python while the main
        // /qc/process call is in flight. Daemon thread so it never blocks shutdown.
        AtomicBoolean stopPoller = new AtomicBoolean(false);
        Thread poller = null;
        if (stageCallback != null) {
            poller = new Thread(() -> pollSubProgress(progressToken, stageCallback, stopPoller),
                    "qc-py-progress-" + progressToken.substring(0, 8));
            poller.setDaemon(true);
            poller.start();
        }

        // Verify PDF file exists before sending
        if (!appraisalPath.toFile().exists()) {
            stopPoller.set(true);
            throw new RuntimeException("Appraisal PDF not found on disk: " + appraisalPath);
        }

        int maxAttempts = Math.max(1, config.getRetryAttempts() + 1);
        try {
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                // Long synchronous OCR+QC call → dedicated long-timeout client (QL-8).
                ResponseEntity<PythonQCResponse> response = processRestTemplate.exchange(
                        url,
                        HttpMethod.POST,
                        requestEntity,
                        PythonQCResponse.class);

                PythonQCResponse result = response.getBody();
                if (result == null) {
                    throw new RuntimeException("Python QC service returned empty response body");
                }
                lastRetryCount.set(Math.max(0, attempt - 1));
                log.info("Python QC completed: passed={}, failed={}, verify={}, total_rules={}",
                        result.passed(), result.failed(), result.verify(), result.totalRules());
                log.info(TimelineLog.event("admin_batches", "java_python_call_complete",
                        "batch_id", batchId,
                        "batch_file_id", batchFileId,
                        "correlation_id", correlationId,
                        "attempt", attempt,
                        "retries", Math.max(0, attempt - 1),
                        "passed", result.passed(),
                        "failed", result.failed(),
                        "verify", result.verify(),
                        "total_rules", result.totalRules(),
                        "python_processing_ms", result.processingTimeMs(),
                        "elapsed_ms", TimelineLog.elapsedMs(callStarted)));
                return result;

            } catch (org.springframework.web.client.HttpClientErrorException e) {
                if (e.getStatusCode().value() == 409) {
                    String runningJobId = extractJobId(e.getResponseBodyAsString());
                    if (runningJobId != null && !runningJobId.isBlank()) {
                        log.warn("Python QC request is already running as job {}; polling existing job instead of failing",
                                runningJobId);
                        lastRetryCount.set(Math.max(0, attempt - 1));
                        return waitForJobResult(
                                runningJobId,
                                Duration.ofSeconds(Math.max(600, (long) config.getTimeoutSeconds() * 4)),
                                null);
                    }
                }
                // 4xx from Python — e.g. 422 invalid PDF, 400 bad request. Retrying will not fix bad input.
                log.error("Python QC service rejected request ({}): {}", e.getStatusCode(), e.getResponseBodyAsString());
                log.error(TimelineLog.event("admin_batches", "java_python_call_rejected",
                        "batch_id", batchId,
                        "batch_file_id", batchFileId,
                        "correlation_id", correlationId,
                        "status", e.getStatusCode(),
                        "elapsed_ms", TimelineLog.elapsedMs(callStarted),
                        "body", e.getResponseBodyAsString()));
                throw new RuntimeException("Python QC service rejected the request: " +
                        e.getStatusCode() + " — " + e.getResponseBodyAsString(), e);
            } catch (org.springframework.web.client.ResourceAccessException e) {
                if (attempt >= maxAttempts) {
                    lastRetryCount.set(Math.max(0, attempt - 1));
                    log.error("Python QC service timeout or connection refused for model {} after {} attempt(s): {}",
                            safeModelConfig.label(), attempt, e.getMessage());
                    log.error(TimelineLog.event("admin_batches", "java_python_call_failed",
                            "batch_id", batchId,
                            "batch_file_id", batchFileId,
                            "correlation_id", correlationId,
                            "attempt", attempt,
                            "elapsed_ms", TimelineLog.elapsedMs(callStarted),
                            "error", e.getMessage()));
                    throw new RuntimeException("Python QC service timed out after " + config.getTimeoutSeconds() + "s " +
                            "while processing model " + safeModelConfig.label() + ". " +
                            "The ocr-service was reachable, but downstream OCR/LLM work may have stalled or timed out.", e);
                }
                log.warn("Python QC attempt {}/{} failed for model {}: {}. Retrying...",
                        attempt, maxAttempts, safeModelConfig.label(), e.getMessage());
                sleepBeforeRetry(attempt);
            } catch (org.springframework.web.client.HttpServerErrorException e) {
                if (attempt >= maxAttempts) {
                    lastRetryCount.set(Math.max(0, attempt - 1));
                    log.error("Python QC service internal error ({}) after {} attempt(s): {}",
                            e.getStatusCode(), attempt, e.getResponseBodyAsString());
                    log.error(TimelineLog.event("admin_batches", "java_python_call_failed",
                            "batch_id", batchId,
                            "batch_file_id", batchFileId,
                            "correlation_id", correlationId,
                            "attempt", attempt,
                            "status", e.getStatusCode(),
                            "elapsed_ms", TimelineLog.elapsedMs(callStarted),
                            "body", e.getResponseBodyAsString()));
                    throw new RuntimeException("Python QC service error: " + e.getStatusCode(), e);
                }
                log.warn("Python QC attempt {}/{} got {} from Python. Retrying...",
                        attempt, maxAttempts, e.getStatusCode());
                sleepBeforeRetry(attempt);
            } catch (RestClientException e) {
                if (attempt >= maxAttempts) {
                    lastRetryCount.set(Math.max(0, attempt - 1));
                    log.error("Failed to call Python QC service after {} attempt(s): {}", attempt, e.getMessage(), e);
                    log.error(TimelineLog.event("admin_batches", "java_python_call_failed",
                            "batch_id", batchId,
                            "batch_file_id", batchFileId,
                            "correlation_id", correlationId,
                            "attempt", attempt,
                            "elapsed_ms", TimelineLog.elapsedMs(callStarted),
                            "error", e.getMessage()));
                    throw new RuntimeException("Python QC service call failed: " + e.getMessage(), e);
                }
                log.warn("Python QC attempt {}/{} failed: {}. Retrying...", attempt, maxAttempts, e.getMessage());
                sleepBeforeRetry(attempt);
            }
        }

        throw new IllegalStateException("Python QC retry loop exited without a result");
        } finally {
            stopPoller.set(true);
            if (poller != null) {
                poller.interrupt();
            }
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

    private static String extractJobId(String body) {
        if (body == null || body.isBlank()) {
            return null;
        }
        Matcher matcher = Pattern.compile("\"job_id\"\\s*:\\s*\"([^\"]+)\"").matcher(body);
        return matcher.find() ? matcher.group(1) : null;
    }

    public static class CeleryWorkerUnavailableException extends RuntimeException {
        private final String jobId;

        public CeleryWorkerUnavailableException(String jobId, String message) {
            super(message);
            this.jobId = jobId;
        }

        public String jobId() {
            return jobId;
        }
    }

    public record PythonProgress(String stage, String message, double subPercent, long elapsedMs) { }

    // ── Async job queue (Celery) ───────────────────────────────────────────────

    /** Response from POST /qc/submit. */
    public record JobSubmitResponse(String jobId, String status, String fileHash) {}

    /**
     * Submit a QC job to the Python Celery queue.
     * Returns immediately with a job_id; caller polls via {@link #waitForJobResult}.
     *
     * @throws RuntimeException if the submit endpoint returns an error
     */
    public JobSubmitResponse submitQCJob(Path appraisalPath, Path engagementPath,
                                         Path contractPath, QCModelConfig modelConfig) {
        return submitQCJob(appraisalPath, engagementPath, contractPath, modelConfig, null, null, null, null, null);
    }

    public JobSubmitResponse submitQCJob(Path appraisalPath, Path engagementPath,
                                         Path contractPath, QCModelConfig modelConfig,
                                         Long batchId, Long batchFileId, Long qcResultId, String sourceHash,
                                         String engagementStatus) {
        return submitQCJob(appraisalPath, null, engagementPath, contractPath,
                modelConfig, batchId, batchFileId, qcResultId, sourceHash, engagementStatus);
    }

    public JobSubmitResponse submitQCJob(Path appraisalPath, Path xmlPath,
                                         Path engagementPath, Path contractPath,
                                         QCModelConfig modelConfig,
                                         Long batchId, Long batchFileId, Long qcResultId, String sourceHash,
                                         String engagementStatus) {
        String url = config.getUrl() + "/qc/submit";
        QCModelConfig cfg = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        lastRetryCount.set(0);

        log.info("Submitting async QC job: appraisal={} xml={} engagement={} contract={} model={}",
                appraisalPath.getFileName(),
                xmlPath        != null ? xmlPath.getFileName()        : "none",
                engagementPath != null ? engagementPath.getFileName() : "none",
                contractPath   != null ? contractPath.getFileName()   : "none",
                cfg.label());

        MultiValueMap<String, Object> body =
                buildBaseBody(appraisalPath, xmlPath, engagementPath, contractPath, engagementStatus, cfg);
        String correlationId = appendProcessingContext(body, batchId, batchFileId, qcResultId, sourceHash, cfg);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        headers.set("X-Correlation-ID", correlationId);
        if (config.getApiKey() != null && !config.getApiKey().isBlank())
            headers.set("X-API-Key", config.getApiKey());

        @SuppressWarnings("rawtypes")
        ResponseEntity<Map> resp = restTemplate.exchange(url, HttpMethod.POST,
                new HttpEntity<>(body, headers), Map.class);

        @SuppressWarnings("unchecked")
        Map<String, Object> rb = resp.getBody();
        if (rb == null) throw new RuntimeException("/qc/submit returned empty body");

        String jobId    = Objects.requireNonNull(stringFromMap(rb, "job_id"), "job_id missing");
        String status   = stringFromMap(rb, "status");
        String fileHash = stringFromMap(rb, "file_hash");
        log.info("QC job queued: jobId={} fileHash={}", jobId, fileHash);
        return new JobSubmitResponse(jobId, status, fileHash);
    }

    /**
     * Poll GET /qc/job/{jobId} until the job reaches SUCCESS or FAILURE, or timeout expires.
     *
     * Checks for batch cancellation on every poll so the thread can be interrupted cleanly.
     *
     * @param jobId           Celery task id returned by {@link #submitQCJob}
     * @param timeout         Maximum total wait time (use config timeout as upper bound)
     * @param batchCancelled  Supplier checked on each poll; throws CancellationException if true
     * @return Full QC response payload
     * @throws RuntimeException on FAILURE status or timeout
     */
    public PythonQCResponse waitForJobResult(String jobId, Duration timeout,
                                              java.util.function.BooleanSupplier batchCancelled) {
        return waitForJobResult(jobId, timeout, batchCancelled, null);
    }

    /**
     * Poll a queued job until done. When {@code progressCallback} is non-null, each
     * poll that returns Celery state=PROGRESS forwards the live stage meta so the
     * async path drives a moving progress bar (not just "queued 2%" until done).
     */
    public PythonQCResponse waitForJobResult(String jobId, Duration timeout,
                                              java.util.function.BooleanSupplier batchCancelled,
                                              Consumer<PythonProgress> progressCallback) {
        String url = config.getUrl() + "/qc/job/" + jobId;
        HttpHeaders headers = new HttpHeaders();
        if (config.getApiKey() != null && !config.getApiKey().isBlank())
            headers.set("X-API-Key", config.getApiKey());
        HttpEntity<Void> entity = new HttpEntity<>(headers);

        Instant deadline        = Instant.now().plus(timeout);
        // If the job stays PENDING (never moves to STARTED) for 180 s the Celery
        // worker is probably not running — surface that early so the caller can
        // fail clearly without starting a duplicate sync request for the same job.
        Instant workerGraceEnd  = Instant.now().plusSeconds(180);
        int pollIntervalMs      = 6_000; // 6 s between polls — a doc takes tens of seconds (OCR + Groq)
        int attempt             = 0;

        while (Instant.now().isBefore(deadline)) {
            if (batchCancelled != null && batchCancelled.getAsBoolean()) {
                throw new java.util.concurrent.CancellationException("QC stopped by admin");
            }

            if (attempt++ > 0) {
                try { Thread.sleep(pollIntervalMs); } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    throw new java.util.concurrent.CancellationException("Interrupted while polling QC job");
                }
            }

            try {
                @SuppressWarnings("rawtypes")
                ResponseEntity<Map> resp = restTemplate.exchange(url, HttpMethod.GET, entity, Map.class);
                @SuppressWarnings("unchecked")
                Map<String, Object> body = resp.getBody();
                if (body == null) continue;

                String state = stringFromMap(body, "status");
                log.debug("QC job {} status={} attempt={}", jobId, state, attempt);

                if ("SUCCESS".equals(state)) {
                    Object resultObj = body.get("result");
                    if (resultObj == null)
                        throw new RuntimeException("QC job " + jobId + " SUCCESS but result is null");
                    try {
                        byte[] json = objectMapper.writeValueAsBytes(resultObj);
                        return objectMapper.readValue(json, PythonQCResponse.class);
                    } catch (Exception je) {
                        throw new RuntimeException("Failed to deserialise QC job result: " + je.getMessage(), je);
                    }
                } else if ("FAILURE".equals(state)) {
                    String err = stringFromMap(body, "error");
                    throw new RuntimeException("QC job " + jobId + " failed: " + err);
                } else if ("PROGRESS".equals(state) && progressCallback != null) {
                    // Live stage meta from the Celery task — drive the progress bar.
                    Object progObj = body.get("progress");
                    if (progObj instanceof Map<?, ?> prog) {
                        Object stageV = prog.get("stage");
                        Object msgV   = prog.get("message");
                        String stage   = stageV != null ? stageV.toString() : "python";
                        String message = msgV != null ? msgV.toString() : "Processing";
                        double pct     = prog.get("sub_percent") instanceof Number n ? n.doubleValue() : 0.0;
                        long elapsed   = prog.get("elapsed_ms")  instanceof Number n ? n.longValue()   : 0L;
                        try {
                            progressCallback.accept(new PythonProgress(stage, message, pct, elapsed));
                        } catch (Exception ignore) { /* progress must never break polling */ }
                    }
                }

                // Still PENDING after grace window → worker is not running, give up fast
                if ("PENDING".equals(state) && Instant.now().isAfter(workerGraceEnd)) {
                    throw new CeleryWorkerUnavailableException(jobId, "Celery worker not running — job " + jobId
                            + " stayed PENDING for >180 s");
                }
                // STARTED / QUEUED / PENDING within grace — keep polling

            } catch (org.springframework.web.client.RestClientException rce) {
                log.warn("Poll attempt {} for job {} failed: {}", attempt, jobId, rce.getMessage());
            } catch (RuntimeException rte) {
                throw rte; // propagate our own exceptions (worker-not-running, deserialise errors)
            }
        }

        throw new RuntimeException("QC job " + jobId + " did not complete within "
                + timeout.toMinutes() + " minutes");
    }

    private void sleepBeforeRetry(int attempt) {
        try {
            Thread.sleep(Math.min(5_000L, attempt * 1_000L));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Interrupted while waiting to retry Python QC request", e);
        }
    }

    /** Expose config so callers can read timeout/retry settings. */
    public OcrServiceConfig getConfig() { return config; }

    public int getLastRetryCount() { return lastRetryCount.get(); }

    public void submitFeedback(PythonFeedbackRequest feedback) {
        if (feedback == null || feedback.documentId() == null || feedback.documentId().isBlank()) {
            return;
        }
        try {
            String url = config.getUrl() + "/qc/feedback";
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            if (config.getApiKey() != null && !config.getApiKey().isBlank()) {
                headers.set("X-API-Key", config.getApiKey());
            }
            restTemplate.exchange(url, HttpMethod.POST, new HttpEntity<>(feedback, headers), String.class);
        } catch (Exception e) {
            log.warn("Python feedback sync skipped for document {} rule {}: {}",
                    feedback.documentId(), feedback.ruleId(), e.getMessage());
        }
    }

    /**
     * Build the multipart body shared by the sync (/qc/process) and async
     * (/qc/submit) calls: the document files, the per-document engagement status,
     * and the model selection. The sync path additionally adds a progress_token;
     * both then call {@link #appendProcessingContext}. Single source of truth for
     * the Python form contract — field names live in exactly one place.
     */
    private MultiValueMap<String, Object> buildBaseBody(
            Path appraisalPath, Path engagementPath, Path contractPath,
            String engagementStatus, QCModelConfig cfg) {
        return buildBaseBody(appraisalPath, null, engagementPath, contractPath, engagementStatus, cfg);
    }

    private MultiValueMap<String, Object> buildBaseBody(
            Path appraisalPath, Path xmlPath, Path engagementPath, Path contractPath,
            String engagementStatus, QCModelConfig cfg) {
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();

        // Guard: appraisal PDF must exist on disk — a missing file causes a silent
        // 422 (FastAPI sees "file" field as null) which is hard to diagnose.
        java.io.File appraisalFile = Objects.requireNonNull(appraisalPath).toFile();
        if (!appraisalFile.exists() || !appraisalFile.isFile()) {
            throw new RuntimeException(
                "Appraisal PDF not found on disk (path: " + appraisalPath + "). " +
                "The file may have been deleted or the storage path is wrong. " +
                "Re-upload the batch to recover.");
        }
        body.add("file", new FileSystemResource(appraisalFile));

        if (xmlPath != null) {
            java.io.File xmlFile = xmlPath.toFile();
            if (xmlFile.exists() && xmlFile.isFile()) {
                body.add("xml_file", new FileSystemResource(xmlFile));
            } else {
                log.warn("APPRAISAL_XML path set ({}) but file not found on disk — skipping XML overlay", xmlPath);
            }
        }
        if (engagementPath != null) {
            java.io.File engFile = engagementPath.toFile();
            if (engFile.exists() && engFile.isFile()) {
                body.add("engagement_letter", new FileSystemResource(engFile));
            } else {
                log.warn("Engagement letter path set ({}) but file not found on disk — skipping", engagementPath);
            }
        }
        if (contractPath != null) {
            java.io.File conFile = contractPath.toFile();
            if (conFile.exists() && conFile.isFile()) {
                body.add("contract_file", new FileSystemResource(conFile));
            } else {
                log.warn("Contract path set ({}) but file not found on disk — skipping", contractPath);
            }
        }
        // Per-document ingestion status so Python's G-0 gate can distinguish a
        // genuinely-absent engagement (NOT_PROVIDED → N/A) from one that exists but
        // failed/awaits extraction (PENDING/EXTRACTION_FAILED → HOLD). Null = let
        // Python use its safe default (absence → HOLD).
        if (engagementStatus != null && !engagementStatus.isBlank()) {
            body.add("engagement_status", engagementStatus);
        }
        body.add("model_provider", cfg.provider());
        body.add("text_model", cfg.textModel());
        body.add("vision_model", cfg.visionModel());
        return body;
    }

    private String appendProcessingContext(MultiValueMap<String, Object> body,
                                         Long batchId, Long batchFileId, Long qcResultId,
                                         String sourceHash, QCModelConfig cfg) {
        String correlationId = org.slf4j.MDC.get("correlationId");
        if (correlationId == null || correlationId.isBlank()) {
            correlationId = batchId != null ? "batch:" + batchId : UUID.randomUUID().toString();
        }
        body.add("correlation_id", correlationId);
        if (batchId != null) body.add("batch_id", String.valueOf(batchId));
        if (batchFileId != null) body.add("batch_file_id", String.valueOf(batchFileId));
        if (qcResultId != null) body.add("qc_result_id", String.valueOf(qcResultId));
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

    public record PythonFeedbackRequest(
            @JsonProperty("document_id") String documentId,
            @JsonProperty("processing_job_id") String processingJobId,
            @JsonProperty("correlation_id") String correlationId,
            @JsonProperty("rule_id") String ruleId,
            @JsonProperty("field_name") String fieldName,
            @JsonProperty("original_value") String originalValue,
            @JsonProperty("corrected_value") String correctedValue,
            @JsonProperty("feedback_type") String feedbackType,
            @JsonProperty("operator_comment") String operatorComment,
            @JsonProperty("reviewer_role") String reviewerRole,
            @JsonProperty("decision_latency_ms") Long decisionLatencyMs,
            @JsonProperty("acknowledged") Boolean acknowledged,
            @JsonProperty("source_page") Integer sourcePage,
            @JsonProperty("bbox_x") Float bboxX,
            @JsonProperty("bbox_y") Float bboxY,
            @JsonProperty("bbox_w") Float bboxW,
            @JsonProperty("bbox_h") Float bboxH,
            @JsonProperty("confidence_score") Double confidenceScore
    ) {}

    /**
     * Check if Python service is healthy.
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

    public boolean isCeleryWorkerRunning() {
        try {
            String url = config.getUrl() + "/health";
            @SuppressWarnings("rawtypes")
            ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
            if (!response.getStatusCode().is2xxSuccessful() || response.getBody() == null) {
                return false;
            }
            return Boolean.TRUE.equals(response.getBody().get("celery_worker_running"));
        } catch (Exception e) {
            log.warn("Python Celery health check failed: {}", e.getMessage());
            return false;
        }
    }

    /**
     * Get list of QC rules from Python service.
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
}
