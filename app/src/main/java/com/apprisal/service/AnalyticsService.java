package com.apprisal.service;

import com.apprisal.common.entity.*;
import com.apprisal.common.repository.*;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

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
    private final QCRuleResultRepository      qcRuleResultRepo;
    private final UserRepository              userRepo;

    public AnalyticsService(ProcessingMetricsRepository metricsRepo,
                            OperatorSessionRepository   sessionRepo,
                            BatchRepository             batchRepo,
                            QCResultRepository          qcResultRepo,
                            QCRuleResultRepository      qcRuleResultRepo,
                            UserRepository              userRepo) {
        this.metricsRepo  = metricsRepo;
        this.sessionRepo  = sessionRepo;
        this.batchRepo    = batchRepo;
        this.qcResultRepo = qcResultRepo;
        this.qcRuleResultRepo = qcRuleResultRepo;
        this.userRepo     = userRepo;
    }

    // ── Overview snapshot ─────────────────────────────────────────────────────

    @Cacheable(cacheNames = "analytics", key = "'overview:' + #days")
    public Map<String, Object> getOverviewSnapshot(int days) {
        LocalDateTime from = LocalDateTime.now().minusDays(days);
        Map<String, Object> snap = new LinkedHashMap<>();

        long totalFiles = metricsRepo.countSince(from);
        snap.put("totalFilesProcessed", totalFiles);
        snap.put("activeSessions", sessionRepo.countByStatus(OperatorSession.Status.ACTIVE));

        Double avgConf = metricsRepo.avgOcrConfidenceSince(from);
        snap.put("avgOcrAccuracy", pctFraction(avgConf));

        Double avgPass = metricsRepo.avgRulePassRateSince(from);
        snap.put("avgRulePassRate", pct(avgPass));

        Double avgMs = metricsRepo.avgProcessingMsSince(from);
        snap.put("avgProcessingSeconds", avgMs != null ? Math.round(avgMs / 1000.0 * 10) / 10.0 : null);

        long cacheHits = metricsRepo.cacheHitCountSince(from);
        snap.put("cacheHitRate", totalFiles > 0 ? pct((double) cacheHits / totalFiles * 100) : 0);

        snap.put("totalBatches", batchRepo.countByStatus(BatchStatus.COMPLETED)
                               + batchRepo.countByStatus(BatchStatus.REVIEW_PENDING));
        snap.put("pendingReview", qcResultRepo.countPendingReviewerWork());
        snap.put("periodDays", days);
        return snap;
    }

    // ── OCR insights ──────────────────────────────────────────────────────────

    @Cacheable(cacheNames = "analytics", key = "'ocr:' + #days")
    public Map<String, Object> getOcrInsights(int days) {
        LocalDateTime from = LocalDateTime.now().minusDays(days);
        Map<String, Object> data = new LinkedHashMap<>();

        data.put("avgAccuracy",     pctFraction(metricsRepo.avgOcrConfidenceSince(from)));
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

    @Cacheable(cacheNames = "analytics", key = "'ml:' + #days")
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

        // QC decision distribution — active results within the window only, so a
        // rerun neither double-counts (old + new) nor leaks results from outside
        // the selected period.
        long autoPass  = qcResultRepo.countActiveByQcDecisionSince(QCDecision.AUTO_PASS, from);
        long toVerify  = qcResultRepo.countActiveByQcDecisionSince(QCDecision.TO_VERIFY, from);
        long autoFail  = qcResultRepo.countActiveByQcDecisionSince(QCDecision.AUTO_FAIL, from);
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

    @Cacheable(cacheNames = "analytics", key = "'operators:' + #days")
    public Map<String, Object> getOperatorInsights(int days) {
        LocalDateTime from = LocalDateTime.now().minusDays(days);
        Map<String, Object> data = new LinkedHashMap<>();

        List<Object[]> rows = sessionRepo.aggregateByUserSince(from);
        // QL-4: batch-fetch all users in ONE query instead of findById per row.
        Map<Long, User> users = usersByIds(rows.stream().map(r -> toLong(r[0])).toList());

        List<Map<String, Object>> operators = new ArrayList<>();
        for (Object[] row : rows) {
            Long userId = toLong(row[0]);
            User user = userId != null ? users.get(userId) : null;
            if (user == null) continue;
            operators.add(Map.of(
                "userId",        userId,
                "name",          user.getFullName() != null ? user.getFullName() : user.getUsername(),
                "activeMinutes", toLong(row[1]) != null ? toLong(row[1]) : 0L,
                "filesProcessed",toLong(row[2]) != null ? toLong(row[2]) : 0L,
                "corrections",   toLong(row[3]) != null ? toLong(row[3]) : 0L
            ));
        }
        data.put("operators", operators);
        data.put("activeNow", sessionRepo.countByStatus(OperatorSession.Status.ACTIVE));
        data.put("periodDays", days);
        return data;
    }

    // ── Daily trend ───────────────────────────────────────────────────────────

    @Cacheable(cacheNames = "analytics", key = "'trend:' + #days")
    public List<Map<String, Object>> getDailyTrend(int days) {
        LocalDateTime from = LocalDateTime.now().minusDays(days);
        List<Map<String, Object>> trend = new ArrayList<>();
        for (Object[] row : metricsRepo.dailyTrendSince(from)) {
            trend.add(Map.of(
                "date",        row[0],
                "ocrAccuracy", pctFraction(toDouble(row[1])),
                "passRate",    pct(toDouble(row[2])),
                "fileCount",   row[3]
            ));
        }
        return trend;
    }

    // ── Supervisor review controls ────────────────────────────────────────────

    @Cacheable(cacheNames = "analytics", key = "'sla'")
    public Map<String, Object> getReviewSlaDashboard() {
        LocalDateTime now = LocalDateTime.now();
        // QL-5: COUNT the 4h/8h totals; fetch only the 50 rows actually shown — not
        // two full entity lists materialised just to call size().
        long over4 = qcRuleResultRepo.countOverdueReviewItems(now.minusHours(4));
        long over8 = qcRuleResultRepo.countOverdueReviewItems(now.minusHours(8));
        List<QCRuleResult> top = qcRuleResultRepo.findOverdueReviewItems(
                now.minusHours(4), PageRequest.of(0, 50));

        List<Map<String, Object>> overdue = top.stream().map(rule -> {
            QCResult qc = rule.getQcResult();
            BatchFile file = qc != null ? qc.getBatchFile() : null;
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("ruleResultId", rule.getId());
            item.put("qcResultId", qc != null ? qc.getId() : "");
            item.put("ruleId", rule.getRuleId());
            item.put("ruleName", rule.getRuleName());
            item.put("firstPresentedAt", rule.getFirstPresentedAt() != null ? rule.getFirstPresentedAt().toString() : "");
            item.put("filename", file != null ? file.getFilename() : "");
            return item;
        }).toList();

        return Map.of(
                "over4Hours", over4,
                "over8Hours", over8,
                "items", overdue
        );
    }

    @Cacheable(cacheNames = "analytics", key = "'anomaly:' + #days")
    public Map<String, Object> getWeeklyAnomalyReport(int days) {
        LocalDateTime from = LocalDateTime.now().minusDays(days);
        List<Object[]> latencyRows  = qcRuleResultRepo.averageDecisionLatencyByReviewerSince(from);
        List<Object[]> overrideRows = qcRuleResultRepo.countFailOverridesByReviewerSince(from);

        // QL-4: one user fetch covering both reports instead of findById per row.
        List<Long> ids = new ArrayList<>();
        latencyRows.forEach(r -> ids.add(toLong(r[0])));
        overrideRows.forEach(r -> ids.add(toLong(r[0])));
        Map<Long, User> users = usersByIds(ids);

        List<Map<String, Object>> fastReviewers = new ArrayList<>();
        for (Object[] row : latencyRows) {
            Long userId = toLong(row[0]);
            Double avgMs = toDouble(row[1]);
            Long count = toLong(row[2]);
            User user = userId != null ? users.get(userId) : null;
            if (user == null || avgMs == null || avgMs >= 6000.0) continue;
            fastReviewers.add(Map.of(
                    "userId", userId,
                    "name", user.getFullName() != null ? user.getFullName() : user.getUsername(),
                    "avgDecisionSeconds", Math.round(avgMs / 100.0) / 10.0,
                    "decisionCount", count != null ? count : 0L,
                    "flag", "Average VERIFY decision time under 6 seconds"
            ));
        }

        List<Map<String, Object>> overrideReviewers = new ArrayList<>();
        for (Object[] row : overrideRows) {
            Long userId = toLong(row[0]);
            Long count = toLong(row[1]);
            User user = userId != null ? users.get(userId) : null;
            if (user == null || count == null || count < 3) continue;
            overrideReviewers.add(Map.of(
                    "userId", userId,
                    "name", user.getFullName() != null ? user.getFullName() : user.getUsername(),
                    "overrideCount", count,
                    "flag", "FAIL override requests above review threshold"
            ));
        }

        return Map.of(
                "periodDays", days,
                "fastDecisionReviewers", fastReviewers,
                "failOverrideReviewers", overrideReviewers
        );
    }

    /** Batch-load users by id into a map (QL-4 — avoids findById-per-row N+1). */
    private Map<Long, User> usersByIds(List<Long> ids) {
        List<Long> clean = ids.stream().filter(Objects::nonNull).distinct().toList();
        if (clean.isEmpty()) return Map.of();
        return userRepo.findAllById(clean).stream()
                .collect(Collectors.toMap(User::getId, u -> u));
    }

    // ── Entity history (Envers) ───────────────────────────────────────────────

    // History queries are exposed directly from the HistoryApiController
    // which uses EnversRevisionRepository — no extra service method needed.

    // ── Helpers ───────────────────────────────────────────────────────────────
    private Double pct(Double v) { return v != null ? Math.round(v * 10.0) / 10.0 : null; }
    /** OCR confidence is persisted as a 0-1 fraction; render it as a 0-100 percentage. */
    private Double pctFraction(Double v) { return v != null ? pct(v * 100.0) : null; }
    private Double toDouble(Object o) { return o instanceof Number n ? n.doubleValue() : null; }
    private Long   toLong(Object o)   { return o instanceof Number n ? n.longValue()   : null; }
}
