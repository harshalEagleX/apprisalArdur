package com.apprisal.service;

import com.apprisal.common.entity.*;
import com.apprisal.common.repository.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.*;

/**
 * Central analytics aggregation service.
 * All data is presented in operator-friendly terms — no technical jargon.
 */
@Service
@Transactional(readOnly = true)
public class AnalyticsService {

    private final ProcessingMetricsRepository metricsRepo;
    private final OperatorSessionRepository   sessionRepo;
    private final BatchRepository             batchRepo;
    private final QCResultRepository          qcResultRepo;
    private final UserRepository              userRepo;

    public AnalyticsService(ProcessingMetricsRepository metricsRepo,
                            OperatorSessionRepository   sessionRepo,
                            BatchRepository             batchRepo,
                            QCResultRepository          qcResultRepo,
                            UserRepository              userRepo) {
        this.metricsRepo  = metricsRepo;
        this.sessionRepo  = sessionRepo;
        this.batchRepo    = batchRepo;
        this.qcResultRepo = qcResultRepo;
        this.userRepo     = userRepo;
    }

    // ── Overview snapshot ─────────────────────────────────────────────────────

    public Map<String, Object> getOverviewSnapshot(int days) {
        LocalDateTime from = LocalDateTime.now().minusDays(days);
        Map<String, Object> snap = new LinkedHashMap<>();

        long totalFiles = metricsRepo.countSince(from);
        snap.put("totalFilesProcessed", totalFiles);
        snap.put("activeSessions", sessionRepo.countByStatus(OperatorSession.Status.ACTIVE));

        Double avgConf = metricsRepo.avgOcrConfidenceSince(from);
        snap.put("avgOcrAccuracy", pct(avgConf));

        Double avgPass = metricsRepo.avgRulePassRateSince(from);
        snap.put("avgRulePassRate", pct(avgPass));

        Double avgMs = metricsRepo.avgProcessingMsSince(from);
        snap.put("avgProcessingSeconds", avgMs != null ? Math.round(avgMs / 1000.0 * 10) / 10.0 : null);

        long cacheHits = metricsRepo.cacheHitCountSince(from);
        snap.put("cacheHitRate", totalFiles > 0 ? pct((double) cacheHits / totalFiles * 100) : 0);

        snap.put("totalBatches", batchRepo.countByStatus(BatchStatus.COMPLETED)
                               + batchRepo.countByStatus(BatchStatus.REVIEW_PENDING));
        snap.put("pendingReview", batchRepo.countByStatus(BatchStatus.REVIEW_PENDING));
        snap.put("periodDays", days);
        return snap;
    }

    // ── OCR insights ──────────────────────────────────────────────────────────

    public Map<String, Object> getOcrInsights(int days) {
        LocalDateTime from = LocalDateTime.now().minusDays(days);
        Map<String, Object> data = new LinkedHashMap<>();

        data.put("avgAccuracy",     pct(metricsRepo.avgOcrConfidenceSince(from)));
        data.put("avgProcessingMs", metricsRepo.avgProcessingMsSince(from));

        List<Map<String, Object>> methods = new ArrayList<>();
        for (Object[] row : metricsRepo.countByExtractionMethodSince(from)) {
            methods.add(Map.of(
                "method", row[0] != null ? row[0] : "unknown",
                "count",  row[1]
            ));
        }
        data.put("extractionMethods", methods);
        data.put("cacheHits", metricsRepo.cacheHitCountSince(from));
        data.put("periodDays", days);
        return data;
    }

    // ── ML / Rules insights ───────────────────────────────────────────────────

    public Map<String, Object> getMlInsights(int days) {
        LocalDateTime from = LocalDateTime.now().minusDays(days);
        Map<String, Object> data = new LinkedHashMap<>();

        data.put("avgRulePassRate", pct(metricsRepo.avgRulePassRateSince(from)));

        List<Map<String, Object>> versions = new ArrayList<>();
        for (Object[] row : metricsRepo.modelVersionStats(from)) {
            versions.add(Map.of(
                "version",      row[0] != null ? row[0] : "unknown",
                "avgPassRate",  pct(toDouble(row[1])),
                "filesAnalysed", row[2]
            ));
        }
        data.put("modelVersions", versions);

        // QC decision distribution
        long autoPass  = qcResultRepo.countByQcDecision(QCDecision.AUTO_PASS);
        long toVerify  = qcResultRepo.countByQcDecision(QCDecision.TO_VERIFY);
        long autoFail  = qcResultRepo.countByQcDecision(QCDecision.AUTO_FAIL);
        long total     = autoPass + toVerify + autoFail;
        data.put("decisionBreakdown", Map.of(
            "autoPassPct",  total > 0 ? pct(autoPass * 100.0 / total) : 0,
            "needsReviewPct", total > 0 ? pct(toVerify * 100.0 / total) : 0,
            "autoFailPct",  total > 0 ? pct(autoFail * 100.0 / total) : 0,
            "autoPass", autoPass, "toVerify", toVerify, "autoFail", autoFail
        ));
        data.put("periodDays", days);
        return data;
    }

    // ── Operator insights ─────────────────────────────────────────────────────

    public Map<String, Object> getOperatorInsights(int days) {
        LocalDateTime from = LocalDateTime.now().minusDays(days);
        Map<String, Object> data = new LinkedHashMap<>();

        List<Map<String, Object>> operators = new ArrayList<>();
        for (Object[] row : sessionRepo.aggregateByUserSince(from)) {
            Long userId = toLong(row[0]);
            if (userId == null) continue;
            userRepo.findById(userId).ifPresent(user -> {
                operators.add(Map.of(
                    "userId",        userId,
                    "name",          user.getFullName() != null ? user.getFullName() : user.getUsername(),
                    "activeMinutes", toLong(row[1]) != null ? toLong(row[1]) : 0L,
                    "filesProcessed",toLong(row[2]) != null ? toLong(row[2]) : 0L,
                    "corrections",   toLong(row[3]) != null ? toLong(row[3]) : 0L
                ));
            });
        }
        data.put("operators", operators);
        data.put("activeNow", sessionRepo.countByStatus(OperatorSession.Status.ACTIVE));
        data.put("periodDays", days);
        return data;
    }

    // ── Daily trend ───────────────────────────────────────────────────────────

    public List<Map<String, Object>> getDailyTrend(int days) {
        LocalDateTime from = LocalDateTime.now().minusDays(days);
        List<Map<String, Object>> trend = new ArrayList<>();
        for (Object[] row : metricsRepo.dailyTrendSince(from)) {
            trend.add(Map.of(
                "date",        row[0],
                "ocrAccuracy", pct(toDouble(row[1])),
                "passRate",    pct(toDouble(row[2])),
                "fileCount",   row[3]
            ));
        }
        return trend;
    }

    // ── Entity history (Envers) ───────────────────────────────────────────────

    // History queries are exposed directly from the HistoryApiController
    // which uses EnversRevisionRepository — no extra service method needed.

    // ── Helpers ───────────────────────────────────────────────────────────────
    private Double pct(Double v) { return v != null ? Math.round(v * 10.0) / 10.0 : null; }
    private Double toDouble(Object o) { return o instanceof Number n ? n.doubleValue() : null; }
    private Long   toLong(Object o)   { return o instanceof Number n ? n.longValue()   : null; }
}
