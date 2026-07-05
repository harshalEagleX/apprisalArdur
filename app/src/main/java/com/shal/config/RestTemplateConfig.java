package com.shal.config;

import com.shal.qc.config.OcrServiceConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

import java.net.http.HttpClient;
import java.time.Duration;

/**
 * HTTP clients for calling the Python OCR/QC service.
 *
 * Scaling QL-8 (readme/SCALABILITY_PLAN.md): there used to be a single RestTemplate
 * (SimpleClientHttpRequestFactory, no pool) whose 900s read timeout was applied to
 * EVERY call — including /live health and progress polls — so a hung Python could
 * block a health check for 15 minutes. We now split into two pooled JDK-HttpClient
 * templates:
 *   - the @Primary short-timeout client for health / submit / poll / rules / feedback,
 *   - a dedicated long-timeout client used only for the synchronous /qc/process fallback.
 * The JDK HttpClient reuses (pools) keep-alive connections, so no Apache dependency.
 */
@Configuration
public class RestTemplateConfig {

    private final OcrServiceConfig ocrServiceConfig;

    public RestTemplateConfig(OcrServiceConfig ocrServiceConfig) {
        this.ocrServiceConfig = ocrServiceConfig;
    }

    /**
     * Default client for SHORT Python calls — /live, /health, /qc/submit, /qc/job,
     * /qc/progress, /qc/rules, /corrections. A 30s read timeout means a stalled
     * Python can never block a health check or a poll for the processing timeout.
     */
    @Bean
    @Primary
    RestTemplate restTemplate() {
        // Force HTTP/1.1: Java's HttpClient negotiates HTTP/2 by default; uvicorn
        // (the Python OCR service) only speaks HTTP/1.1 and rejects h2c upgrade
        // requests with "Invalid HTTP request received." (400 Bad Request).
        HttpClient httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .version(HttpClient.Version.HTTP_1_1)
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(Duration.ofSeconds(30));
        return new RestTemplate(factory);
    }

    /**
     * Dedicated client for the LONG synchronous /qc/process fallback ONLY (used by
     * PythonClientService.processQC). Read timeout tracks the configured OCR timeout
     * (minutes). Once the Celery queue (Phase 1) is the default path, this is exercised
     * only when no Celery worker is running.
     */
    @Bean("pythonProcessRestTemplate")
    RestTemplate pythonProcessRestTemplate() {
        // Force HTTP/1.1 — same reason as above.
        HttpClient httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .version(HttpClient.Version.HTTP_1_1)
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(Duration.ofSeconds(Math.max(60, ocrServiceConfig.getTimeoutSeconds())));
        return new RestTemplate(factory);
    }
}
