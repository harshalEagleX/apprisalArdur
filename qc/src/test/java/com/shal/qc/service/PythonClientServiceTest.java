package com.shal.qc.service;

import com.shal.common.dto.python.PythonQCResponse;
import com.shal.qc.config.OcrServiceConfig;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;
import tools.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Regression coverage for the Java→Python integration path in PythonClientService
 * (REGRESSION_AUDIT.md risk #3 — previously "no test"). Exercises the retry loop,
 * 4xx no-retry, timeout exhaustion, 409 job-dedup polling, and the /qc/rules proxy,
 * all with mocked RestTemplates so no live Python service is required.
 */
class PythonClientServiceTest {

    private RestTemplate shortRt;     // health/poll/job/rules — first constructor arg
    private RestTemplate processRt;   // long-timeout /qc/process — second constructor arg
    private OcrServiceConfig config;
    private PythonClientService svc;
    private Path appraisal;

    @BeforeEach
    void setUp(@TempDir Path tmp) throws Exception {
        shortRt = mock(RestTemplate.class);
        processRt = mock(RestTemplate.class);
        config = new OcrServiceConfig();
        config.setUrl("http://py.test:5001");
        config.setApiKey("test-key");
        config.setRetryAttempts(2);
        config.setTimeoutSeconds(5);
        svc = new PythonClientService(shortRt, processRt, config, new ObjectMapper());
        appraisal = tmp.resolve("appraisal.pdf");
        Files.writeString(appraisal, "%PDF-1.4 fake appraisal");
    }

    private static HttpClientErrorException clientError(HttpStatus status, String body) {
        return HttpClientErrorException.create(status, status.getReasonPhrase(),
                HttpHeaders.EMPTY, body.getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
    }

    @Test
    void happyPath_returnsResponse_withoutRetrying() {
        PythonQCResponse body = mock(PythonQCResponse.class);
        when(processRt.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(PythonQCResponse.class)))
                .thenReturn(new ResponseEntity<>(body, HttpStatus.OK));

        PythonQCResponse result = svc.processQC(appraisal, null);

        assertThat(result).isSameAs(body);
        assertThat(svc.getLastRetryCount()).isZero();
        verify(processRt, times(1)).exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(PythonQCResponse.class));
    }

    @Test
    void emptyBody_throws() {
        when(processRt.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(PythonQCResponse.class)))
                .thenReturn(new ResponseEntity<>((PythonQCResponse) null, HttpStatus.OK));

        assertThatThrownBy(() -> svc.processQC(appraisal, null))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("empty response body");
    }

    @Test
    void retriesOnServerError_thenSucceeds() {
        config.setRetryAttempts(1); // 2 attempts total → one ~1s backoff
        PythonQCResponse body = mock(PythonQCResponse.class);
        when(processRt.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(PythonQCResponse.class)))
                .thenThrow(new HttpServerErrorException(HttpStatus.INTERNAL_SERVER_ERROR))
                .thenReturn(new ResponseEntity<>(body, HttpStatus.OK));

        PythonQCResponse result = svc.processQC(appraisal, null);

        assertThat(result).isSameAs(body);
        assertThat(svc.getLastRetryCount()).isEqualTo(1);
        verify(processRt, times(2)).exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(PythonQCResponse.class));
    }

    @Test
    void timeoutExhausted_throwsTimedOut() {
        config.setRetryAttempts(0); // single attempt, no backoff sleep
        when(processRt.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(PythonQCResponse.class)))
                .thenThrow(new ResourceAccessException("connection timed out"));

        assertThatThrownBy(() -> svc.processQC(appraisal, null))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("timed out");
    }

    @Test
    void clientError4xx_doesNotRetry() {
        when(processRt.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(PythonQCResponse.class)))
                .thenThrow(clientError(HttpStatus.UNPROCESSABLE_ENTITY, "invalid pdf"));

        assertThatThrownBy(() -> svc.processQC(appraisal, null))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("rejected");
        verify(processRt, times(1)).exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(PythonQCResponse.class));
    }

    @Test
    void conflict409_pollsExistingJobInsteadOfFailing() {
        when(processRt.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(PythonQCResponse.class)))
                .thenThrow(clientError(HttpStatus.CONFLICT, "{\"job_id\":\"job-123\"}"));
        // The dedup path polls GET /qc/job/{id} on the short-timeout client.
        when(shortRt.exchange(contains("/qc/job/job-123"), eq(HttpMethod.GET), any(HttpEntity.class), eq(Map.class)))
                .thenReturn(new ResponseEntity<>(Map.of("status", "FAILURE", "error", "boom"), HttpStatus.OK));

        assertThatThrownBy(() -> svc.processQC(appraisal, null))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("failed");
        verify(shortRt).exchange(contains("/qc/job/job-123"), eq(HttpMethod.GET), any(HttpEntity.class), eq(Map.class));
    }

    @Test
    void getRules_returnsBody() {
        when(shortRt.exchange(contains("/qc/rules"), eq(HttpMethod.GET), any(HttpEntity.class), eq(String.class)))
                .thenReturn(new ResponseEntity<>("{\"total\":2,\"rules\":[{\"rule_id\":\"S-1\"}]}", HttpStatus.OK));

        assertThat(svc.getRules()).contains("S-1");
    }

    @Test
    void getRules_returnsNullOnError() {
        when(shortRt.exchange(contains("/qc/rules"), eq(HttpMethod.GET), any(HttpEntity.class), eq(String.class)))
                .thenThrow(new ResourceAccessException("down"));

        assertThat(svc.getRules()).isNull();
    }
}
