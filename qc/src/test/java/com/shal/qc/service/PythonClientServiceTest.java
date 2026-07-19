package com.shal.qc.service;

import com.shal.qc.config.OcrServiceConfig;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.when;

/**
 * The Java → Python boundary.
 *
 * Every call here is a network call to a service that can be down, slow, or
 * behind an API key. The contract that matters is the DEGRADATION: a failing
 * Python service must return a falsy/null answer that the caller degrades on,
 * never propagate an exception up into a reviewer request. This class was at 0%.
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class PythonClientServiceTest {

    @Mock RestTemplate restTemplate;
    @Mock RestTemplate processRestTemplate;
    @Mock OcrServiceConfig config;

    private PythonClientService svc;

    @BeforeEach
    void setUp() {
        when(config.getUrl()).thenReturn("http://python:5001");
        svc = new PythonClientService(restTemplate, processRestTemplate, config);
    }

    // ── liveness ────────────────────────────────────────────────────────────

    @Test
    @DisplayName("a 2xx from /live means healthy")
    void healthyOn2xx() {
        when(restTemplate.getForEntity("http://python:5001/live", String.class))
                .thenReturn(new ResponseEntity<>("ok", HttpStatus.OK));
        assertThat(svc.isHealthy()).isTrue();
    }

    @Test
    @DisplayName("a non-2xx means NOT healthy")
    void unhealthyOnNon2xx() {
        when(restTemplate.getForEntity(anyString(), eq(String.class)))
                .thenReturn(new ResponseEntity<>("nope", HttpStatus.SERVICE_UNAVAILABLE));
        assertThat(svc.isHealthy()).isFalse();
    }

    @Test
    @DisplayName("a transport failure reports unhealthy instead of throwing at the caller")
    void unhealthyOnException() {
        // Python being down must not surface as a 500 on a reviewer page.
        when(restTemplate.getForEntity(anyString(), eq(String.class)))
                .thenThrow(new RestClientException("connection refused"));
        assertThat(svc.isHealthy()).isFalse();
    }

    @Test
    @DisplayName("liveness uses /live, not the heavier /health")
    void usesLiveEndpoint() {
        when(restTemplate.getForEntity(anyString(), eq(String.class)))
                .thenReturn(new ResponseEntity<>("ok", HttpStatus.OK));
        svc.isHealthy();
        // /health does DB checks; the liveness probe must stay instant.
        org.mockito.Mockito.verify(restTemplate)
                .getForEntity("http://python:5001/live", String.class);
    }

    // ── rules passthrough ───────────────────────────────────────────────────

    @Test
    @DisplayName("getRules returns the body verbatim")
    void rulesReturnsBody() {
        when(restTemplate.exchange(anyString(), eq(HttpMethod.GET), any(), eq(String.class)))
                .thenReturn(new ResponseEntity<>("[{\"id\":\"S-1\"}]", HttpStatus.OK));
        assertThat(svc.getRules()).isEqualTo("[{\"id\":\"S-1\"}]");
    }

    @Test
    @DisplayName("getRules degrades to null when Python is unreachable")
    void rulesNullOnFailure() {
        when(restTemplate.exchange(anyString(), eq(HttpMethod.GET), any(), eq(String.class)))
                .thenThrow(new RestClientException("timeout"));
        assertThat(svc.getRules()).isNull();
    }

    @Test
    @DisplayName("the API key is sent when configured")
    void apiKeyForwardedWhenPresent() {
        when(config.getApiKey()).thenReturn("secret-key");
        when(restTemplate.exchange(anyString(), eq(HttpMethod.GET), any(), eq(String.class)))
                .thenAnswer(inv -> {
                    HttpEntity<?> entity = inv.getArgument(2);
                    assertThat(entity.getHeaders().getFirst("X-API-Key")).isEqualTo("secret-key");
                    return new ResponseEntity<>("[]", HttpStatus.OK);
                });
        assertThat(svc.getRules()).isEqualTo("[]");
    }

    @Test
    @DisplayName("no API-Key header is sent when the key is absent or blank")
    void apiKeyOmittedWhenBlank() {
        when(config.getApiKey()).thenReturn("   ");
        when(restTemplate.exchange(anyString(), eq(HttpMethod.GET), any(), eq(String.class)))
                .thenAnswer(inv -> {
                    HttpEntity<?> entity = inv.getArgument(2);
                    assertThat(entity.getHeaders().getFirst("X-API-Key")).isNull();
                    return new ResponseEntity<>("[]", HttpStatus.OK);
                });
        svc.getRules();
    }

    // ── correction proxy ────────────────────────────────────────────────────

    @Test
    @DisplayName("submitCorrection returns Python's body so the caller can pass it through")
    void correctionReturnsBody() {
        when(restTemplate.exchange(anyString(), eq(HttpMethod.POST), any(), eq(String.class)))
                .thenReturn(new ResponseEntity<>("{\"ok\":true}", HttpStatus.OK));
        assertThat(svc.submitCorrection(java.util.Map.of("field", "x")))
                .isEqualTo("{\"ok\":true}");
    }

    @Test
    @DisplayName("submitCorrection THROWS on failure — a write must not fail silently")
    void correctionThrowsOnFailure() {
        // Deliberate asymmetry with the reads above: isHealthy/getRules degrade to
        // false/null because a stale read is survivable, but a correction is a
        // reviewer WRITE. Swallowing that would tell them their change was saved
        // when it was not, so the failure propagates and the caller surfaces it.
        when(restTemplate.exchange(anyString(), eq(HttpMethod.POST), any(), eq(String.class)))
                .thenThrow(new RestClientException("boom"));
        org.assertj.core.api.Assertions
                .assertThatThrownBy(() -> svc.submitCorrection(java.util.Map.of("field", "x")))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("Failed to submit correction");
    }

    @Test
    @DisplayName("a correction is POSTed as JSON to /corrections")
    void correctionPostsJsonToCorrectionsEndpoint() {
        when(restTemplate.exchange(anyString(), eq(HttpMethod.POST), any(), eq(String.class)))
                .thenAnswer(inv -> {
                    assertThat((String) inv.getArgument(0)).endsWith("/corrections");
                    HttpEntity<?> entity = inv.getArgument(2);
                    assertThat(entity.getHeaders().getContentType())
                            .hasToString("application/json");
                    return new ResponseEntity<>("{}", HttpStatus.OK);
                });
        svc.submitCorrection(java.util.Map.of("field", "x"));
    }

    // ── retry counter ───────────────────────────────────────────────────────

    @Test
    @DisplayName("the retry counter starts at zero for a fresh thread")
    void retryCountStartsAtZero() {
        assertThat(svc.getLastRetryCount()).isZero();
    }
}
