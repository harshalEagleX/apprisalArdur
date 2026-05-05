package com.apprisal.qc.service;

import com.apprisal.qc.config.OcrServiceConfig;
import com.apprisal.common.dto.python.PythonQCResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.nio.file.Path;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

/**
 * Service for calling the Python OCR/QC service.
 * Handles HTTP communication with Python /qc/process endpoint.
 */
@Service
public class PythonClientService {

    private static final Logger log = LoggerFactory.getLogger(PythonClientService.class);

    private final RestTemplate restTemplate;
    private final OcrServiceConfig config;

    public PythonClientService(RestTemplate restTemplate, OcrServiceConfig config) {
        this.restTemplate = restTemplate;
        this.config = config;
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
        String url = config.getUrl() + "/qc/process";
        QCModelConfig safeModelConfig = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        String progressToken = UUID.randomUUID().toString();

        log.info("Calling Python QC service: {} with appraisal: {}, engagement: {}, contract: {}, model: {}",
                url, appraisalPath.getFileName(),
                engagementPath != null ? engagementPath.getFileName() : "none",
                contractPath != null ? contractPath.getFileName() : "none",
                safeModelConfig.label());

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file", new FileSystemResource(Objects.requireNonNull(appraisalPath.toFile())));

        if (engagementPath != null) {
            body.add("engagement_letter", new FileSystemResource(Objects.requireNonNull(engagementPath.toFile())));
        }

        if (contractPath != null) {
            body.add("contract_file", new FileSystemResource(Objects.requireNonNull(contractPath.toFile())));
        }
        body.add("model_provider", safeModelConfig.provider());
        body.add("text_model", safeModelConfig.textModel());
        body.add("vision_model", safeModelConfig.visionModel());
        body.add("progress_token", progressToken);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
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
                ResponseEntity<PythonQCResponse> response = restTemplate.exchange(
                        url,
                        HttpMethod.POST,
                        requestEntity,
                        PythonQCResponse.class);

                PythonQCResponse result = response.getBody();
                if (result == null) {
                    throw new RuntimeException("Python QC service returned empty response body");
                }
                log.info("Python QC completed: passed={}, failed={}, verify={}, total_rules={}",
                        result.passed(), result.failed(), result.verify(), result.totalRules());
                return result;

            } catch (org.springframework.web.client.HttpClientErrorException e) {
                // 4xx from Python — e.g. 422 invalid PDF, 400 bad request. Retrying will not fix bad input.
                log.error("Python QC service rejected request ({}): {}", e.getStatusCode(), e.getResponseBodyAsString());
                throw new RuntimeException("Python QC service rejected the request: " +
                        e.getStatusCode() + " — " + e.getResponseBodyAsString(), e);
            } catch (org.springframework.web.client.ResourceAccessException e) {
                if (attempt >= maxAttempts) {
                    log.error("Python QC service timeout or connection refused for model {} after {} attempt(s): {}",
                            safeModelConfig.label(), attempt, e.getMessage());
                    throw new RuntimeException("Python QC service timed out after " + config.getTimeoutSeconds() + "s " +
                            "while processing model " + safeModelConfig.label() + ". " +
                            "The ocr-service was reachable, but downstream OCR/LLM work may have stalled or timed out.", e);
                }
                log.warn("Python QC attempt {}/{} failed for model {}: {}. Retrying...",
                        attempt, maxAttempts, safeModelConfig.label(), e.getMessage());
                sleepBeforeRetry(attempt);
            } catch (org.springframework.web.client.HttpServerErrorException e) {
                if (attempt >= maxAttempts) {
                    log.error("Python QC service internal error ({}) after {} attempt(s): {}",
                            e.getStatusCode(), attempt, e.getResponseBodyAsString());
                    throw new RuntimeException("Python QC service error: " + e.getStatusCode(), e);
                }
                log.warn("Python QC attempt {}/{} got {} from Python. Retrying...",
                        attempt, maxAttempts, e.getStatusCode());
                sleepBeforeRetry(attempt);
            } catch (RestClientException e) {
                if (attempt >= maxAttempts) {
                    log.error("Failed to call Python QC service after {} attempt(s): {}", attempt, e.getMessage(), e);
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

    public record PythonProgress(String stage, String message, double subPercent, long elapsedMs) { }

    private void sleepBeforeRetry(int attempt) {
        try {
            Thread.sleep(Math.min(5_000L, attempt * 1_000L));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Interrupted while waiting to retry Python QC request", e);
        }
    }

    /**
     * Check if Python service is healthy.
     */
    public boolean isHealthy() {
        try {
            String url = config.getUrl() + "/health";
            ResponseEntity<String> response = restTemplate.getForEntity(url, String.class);
            return response.getStatusCode().is2xxSuccessful();
        } catch (Exception e) {
            log.warn("Python service health check failed: {}", e.getMessage());
            return false;
        }
    }

    /**
     * Get list of QC rules from Python service.
     */
    public String getRules() {
        try {
            String url = config.getUrl() + "/qc/rules";
            ResponseEntity<String> response = restTemplate.getForEntity(url, String.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("Failed to get QC rules: {}", e.getMessage());
            return null;
        }
    }
}
