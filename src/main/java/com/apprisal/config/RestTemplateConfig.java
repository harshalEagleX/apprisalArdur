package com.apprisal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

/**
 * Configuration for RestTemplate used to call external services (Python OCR).
 */
@Configuration
public class RestTemplateConfig {

    private final OcrServiceConfig ocrServiceConfig;

    public RestTemplateConfig(OcrServiceConfig ocrServiceConfig) {
        this.ocrServiceConfig = ocrServiceConfig;
    }

    @Bean
    RestTemplate restTemplate() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(10000); // 10 seconds
        factory.setReadTimeout(ocrServiceConfig.getTimeoutSeconds() * 1000);
        return new RestTemplate(factory);
    }
}
