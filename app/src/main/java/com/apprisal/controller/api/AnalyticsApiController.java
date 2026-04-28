package com.apprisal.controller.api;

import com.apprisal.service.AnalyticsService;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Analytics REST API — feeds the operator, OCR, ML, and system dashboards.
 * All responses use plain language — no ML/OCR jargon exposed to operators.
 */
@RestController
@RequestMapping("/api/analytics")
public class AnalyticsApiController {

    private final AnalyticsService analyticsService;

    public AnalyticsApiController(AnalyticsService analyticsService) {
        this.analyticsService = analyticsService;
    }

    /** Quick-look summary for dashboard header cards. */
    @GetMapping("/overview")
    @PreAuthorize("hasAnyRole('ADMIN', 'REVIEWER')")
    public ResponseEntity<Map<String, Object>> overview(
            @RequestParam(defaultValue = "30") int days) {
        return ResponseEntity.ok(analyticsService.getOverviewSnapshot(days));
    }

    /** OCR quality stats — accuracy, extraction method, processing speed. */
    @GetMapping("/ocr")
    @PreAuthorize("hasAnyRole('ADMIN', 'REVIEWER')")
    public ResponseEntity<Map<String, Object>> ocr(
            @RequestParam(defaultValue = "30") int days) {
        return ResponseEntity.ok(analyticsService.getOcrInsights(days));
    }

    /** ML/rules insights — pass rates, decision distribution, model versions. */
    @GetMapping("/ml")
    @PreAuthorize("hasAnyRole('ADMIN', 'REVIEWER')")
    public ResponseEntity<Map<String, Object>> ml(
            @RequestParam(defaultValue = "30") int days) {
        return ResponseEntity.ok(analyticsService.getMlInsights(days));
    }

    /** Operator performance — hours worked, files processed, correction rate. */
    @GetMapping("/operators")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> operators(
            @RequestParam(defaultValue = "30") int days) {
        return ResponseEntity.ok(analyticsService.getOperatorInsights(days));
    }

    /** Day-by-day trend for charts. */
    @GetMapping("/trend")
    @PreAuthorize("hasAnyRole('ADMIN', 'REVIEWER')")
    public ResponseEntity<?> trend(
            @RequestParam(defaultValue = "30") int days) {
        return ResponseEntity.ok(analyticsService.getDailyTrend(days));
    }
}
