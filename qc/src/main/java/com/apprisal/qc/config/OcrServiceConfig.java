package com.apprisal.qc.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "ocr.service")
public class OcrServiceConfig {

    private String url = "http://localhost:5001";
    private int timeoutSeconds = 180;
    private int retryAttempts = 2;
    /** Sent as X-API-Key header to the Python service. Empty = dev mode (no auth). */
    private String apiKey = "";

    public String getUrl()              { return url; }
    public void   setUrl(String u)      { this.url = u; }
    public int    getTimeoutSeconds()   { return timeoutSeconds; }
    public void   setTimeoutSeconds(int t) { this.timeoutSeconds = t; }
    public int    getRetryAttempts()    { return retryAttempts; }
    public void   setRetryAttempts(int r)  { this.retryAttempts = r; }
    public String getApiKey()           { return apiKey; }
    public void   setApiKey(String k)   { this.apiKey = k; }
}
