package com.shal.metrics;

import com.shal.common.entity.BatchStatus;
import com.shal.common.repository.BatchRepository;
import com.shal.common.util.AppTime;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

/**
 * Business-level QC metrics exposed to Prometheus via /actuator/prometheus.
 *
 * Micrometer already auto-binds Hikari pool, JVM, and HTTP timings; this adds the
 * domain gauges that the alert rules (prometheus/alert.rules.yml) watch:
 *   - backlog depth per workflow status
 *   - stuck-in-processing count (batches older than the reconciler retry window)
 *
 * Gauges are sampled on scrape via cheap COUNT-by-indexed-status queries — no
 * background thread, no extra state. A query hiccup surfaces as a NaN sample
 * rather than an error, so metrics never destabilise the app.
 */
@Component
public class QcMetrics {

    /** Batches in QC_PROCESSING longer than this are considered "stuck" for the gauge. */
    private static final int STUCK_MINUTES = 15;

    public QcMetrics(MeterRegistry registry, BatchRepository batchRepository) {
        gauge(registry, "shal.batches.qc_processing",
                "Batches currently in QC_PROCESSING",
                () -> batchRepository.countByStatus(BatchStatus.QC_PROCESSING));

        gauge(registry, "shal.batches.review_pending",
                "Batches waiting for a reviewer to pick up",
                () -> batchRepository.countByStatus(BatchStatus.REVIEW_PENDING));

        gauge(registry, "shal.batches.in_review",
                "Batches actively being reviewed",
                () -> batchRepository.countByStatus(BatchStatus.IN_REVIEW));

        gauge(registry, "shal.batches.error",
                "Batches in ERROR awaiting investigation",
                () -> batchRepository.countByStatus(BatchStatus.ERROR));

        gauge(registry, "shal.batches.qc_stuck",
                "Batches stuck in QC_PROCESSING beyond the reconciler retry window",
                () -> {
                    try {
                        return batchRepository
                                .findStuckInQcProcessing(AppTime.now().minusMinutes(STUCK_MINUTES))
                                .size();
                    } catch (Exception e) {
                        return Double.NaN;
                    }
                });
    }

    private static void gauge(MeterRegistry registry, String name, String description,
                              java.util.function.Supplier<Number> supplier) {
        Gauge.builder(name, supplier)
                .description(description)
                .strongReference(true)
                .register(registry);
    }
}
