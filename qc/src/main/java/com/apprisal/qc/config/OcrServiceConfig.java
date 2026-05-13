package com.apprisal.qc.config;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "ocr.service")
public class OcrServiceConfig {

    private static final Logger log = LoggerFactory.getLogger(OcrServiceConfig.class);

    private String url = "http://localhost:5001";
    private int timeoutSeconds = 180;
    private int retryAttempts = 2;
    /** Sent as X-API-Key header to the Python service. Required. */
    private String apiKey = "";

    @PostConstruct
    public void validate() {
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalStateException(
                    "Missing required INTERNAL_API_KEY. Define it once in the project root .env " +
                            "or export it before starting Java and Python."
            );
        }

        log.info("ocr.service.api-key loaded from INTERNAL_API_KEY ({}...), target={}",
                apiKey.substring(0, Math.min(6, apiKey.length())), url);
    }

    public String getUrl()              { return url; }
    public void   setUrl(String u)      { this.url = u; }
    public int    getTimeoutSeconds()   { return timeoutSeconds; }
    public void   setTimeoutSeconds(int t) { this.timeoutSeconds = t; }
    public int    getRetryAttempts()    { return retryAttempts; }
    public void   setRetryAttempts(int r)  { this.retryAttempts = r; }
    public String getApiKey()           { return apiKey; }
    public void   setApiKey(String k)   { this.apiKey = k; }
}
