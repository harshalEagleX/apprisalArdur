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
import java.util.Objects;

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
        String url = config.getUrl() + "/qc/process";
        QCModelConfig safeModelConfig = modelConfig != null ? modelConfig : QCModelConfig.defaults();

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

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        // SECURITY: send API key to Python service
        if (config.getApiKey() != null && !config.getApiKey().isBlank()) {
            headers.set("X-API-Key", config.getApiKey());
        }

        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

        // Verify PDF file exists before sending
        if (!appraisalPath.toFile().exists()) {
            throw new RuntimeException("Appraisal PDF not found on disk: " + appraisalPath);
        }

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
            log.info("Python QC completed: passed={}, failed={}, warnings={}, total_rules={}",
                    result.passed(), result.failed(), result.warnings(), result.totalRules());
            return result;

        } catch (org.springframework.web.client.ResourceAccessException e) {
            // Timeout or connection refused
            log.error("Python QC service timeout or connection refused: {}", e.getMessage());
            throw new RuntimeException("Python QC service timeout (limit: " + config.getTimeoutSeconds() + "s). " +
                    "Check that ocr-service is running and responsive.", e);
        } catch (org.springframework.web.client.HttpClientErrorException e) {
            // 4xx from Python — e.g. 422 invalid PDF, 400 bad request
            log.error("Python QC service rejected request ({}): {}", e.getStatusCode(), e.getResponseBodyAsString());
            throw new RuntimeException("Python QC service rejected the request: " +
                    e.getStatusCode() + " — " + e.getResponseBodyAsString(), e);
        } catch (org.springframework.web.client.HttpServerErrorException e) {
            // 5xx from Python
            log.error("Python QC service internal error ({}): {}", e.getStatusCode(), e.getResponseBodyAsString());
            throw new RuntimeException("Python QC service error: " + e.getStatusCode(), e);
        } catch (RestClientException e) {
            log.error("Failed to call Python QC service: {}", e.getMessage(), e);
            throw new RuntimeException("Python QC service call failed: " + e.getMessage(), e);
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
