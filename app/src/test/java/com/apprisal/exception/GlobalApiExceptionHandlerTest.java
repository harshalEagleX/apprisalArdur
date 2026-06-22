package com.apprisal.exception;

import com.apprisal.common.exception.ValidationException;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.orm.ObjectOptimisticLockingFailureException;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Regression coverage for GlobalApiExceptionHandler. The headline case is the
 * a16bcfa fix: a malformed/empty request body must map to 400, not the generic 500
 * (REGRESSION_AUDIT.md — "malformed QC request → 500 (now 400)"). Also pins the
 * optimistic-lock → 409 mapping that protects the concurrent-reviewer edit path.
 */
class GlobalApiExceptionHandlerTest {

    private final GlobalApiExceptionHandler handler = new GlobalApiExceptionHandler();

    @Test
    void malformedOrMissingBody_maps400() {
        ResponseEntity<Map<String, Object>> resp =
                handler.handleUnreadableBody(new HttpMessageNotReadableException("boom", (HttpInputMessage) null));

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(resp.getBody()).containsEntry("status", 400);
        assertThat(resp.getBody()).containsKey("message");
    }

    @Test
    void illegalArgument_maps400() {
        ResponseEntity<Map<String, Object>> resp =
                handler.handleIllegalArgument(new IllegalArgumentException("bad input"));

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(resp.getBody()).containsEntry("status", 400);
    }

    @Test
    void validationException_maps400_andCarriesField() {
        ResponseEntity<Map<String, Object>> resp =
                handler.handleValidation(new ValidationException("name", "name is required"));

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(resp.getBody()).containsEntry("field", "name");
    }

    @Test
    void optimisticLock_maps409_forConcurrentReviewerEdits() {
        ResponseEntity<Map<String, Object>> resp =
                handler.handleOptimisticLock(new ObjectOptimisticLockingFailureException("stale", new RuntimeException()));

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.CONFLICT);
        assertThat(resp.getBody()).containsEntry("status", 409);
    }

    @Test
    void unexpectedException_maps500_withGenericMessage() {
        ResponseEntity<Map<String, Object>> resp =
                handler.handleGenericException(new Exception("internal detail that must not leak"));

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(resp.getBody()).containsEntry("status", 500);
        // The raw exception message must not be surfaced to the client.
        assertThat(resp.getBody().get("message").toString()).doesNotContain("internal detail");
    }
}
