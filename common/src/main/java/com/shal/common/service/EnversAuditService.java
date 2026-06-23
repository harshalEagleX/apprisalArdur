package com.shal.common.service;

import com.shal.common.audit.AppRevisionEntity;
import com.shal.common.entity.QCResult;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.hibernate.envers.AuditReaderFactory;
import org.hibernate.envers.RevisionType;
import org.hibernate.envers.query.AuditEntity;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.*;

/**
 * Reads Hibernate Envers revision history for audited entities.
 *
 * Envers writes revision rows into *_aud tables on every JPA transaction.
 * This service exposes that accumulated history as a field-level diff timeline
 * for the audit graph's QC_RUN node drawer and the diff endpoint.
 *
 * Only scalar fields are compared — LAZY associations (reviewedBy, batchFile,
 * rerunOf) are never accessed so the diff is a single-pass read with no N+1.
 */
@Service
@Transactional(readOnly = true)
public class EnversAuditService {

    private static final Logger log = LoggerFactory.getLogger(EnversAuditService.class);

    @PersistenceContext
    private EntityManager entityManager;

    /**
     * Returns the full revision history for a single QCResult, oldest first.
     * Each entry identifies what changed, who changed it, and when.
     *
     * Returns an empty list if Envers has no rows for this ID (entity created
     * before auditing was enabled, or the aud table was recently wiped).
     */
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> getQCResultRevisions(Long qcResultId) {
        try {
            var reader = AuditReaderFactory.get(entityManager);

            List<Object[]> history = reader.createQuery()
                .forRevisionsOfEntity(QCResult.class, false, true)
                .add(AuditEntity.id().eq(qcResultId))
                .addOrder(AuditEntity.revisionNumber().asc())
                .getResultList();

            List<Map<String, Object>> result = new ArrayList<>();
            QCResult prev = null;

            for (Object[] row : history) {
                QCResult          snapshot = (QCResult) row[0];
                AppRevisionEntity revInfo  = (AppRevisionEntity) row[1];
                RevisionType      revType  = (RevisionType) row[2];

                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("revision",      revInfo.getId());
                entry.put("revisionType",  revType.name());
                entry.put("changedAt",     revInfo.getRevisionInstant().toString());
                entry.put("changedBy",     revInfo.getUsername());
                entry.put("ipAddress",     revInfo.getIpAddress());
                entry.put("correlationId", revInfo.getCorrelationId());
                entry.put("action",        summarizeAction(prev, snapshot, revType));
                entry.put("changes",       computeChanges(prev, snapshot));

                result.add(entry);
                prev = snapshot;
            }

            log.debug("[envers] qcResultId={} → {} revisions", qcResultId, result.size());
            return result;
        } catch (Exception e) {
            log.warn("[envers] revision query failed for qcResultId={}: {}", qcResultId, e.getMessage());
            return List.of();
        }
    }

    // ── Field-level diff ───────────────────────────────────────────────────────

    private static Map<String, Object> computeChanges(QCResult prev, QCResult curr) {
        Map<String, Object> out = new LinkedHashMap<>();

        // Scalar fields only — never access LAZY associations (reviewedBy, batchFile, etc.)
        diff(out, "qcDecision",
            prev != null && prev.getQcDecision()   != null ? prev.getQcDecision().name()   : null,
            curr.getQcDecision()   != null ? curr.getQcDecision().name()   : null);
        diff(out, "finalDecision",
            prev != null && prev.getFinalDecision() != null ? prev.getFinalDecision().name() : null,
            curr.getFinalDecision() != null ? curr.getFinalDecision().name() : null);
        diff(out, "passedCount",     boxed(prev, QCResult::getPassedCount),    curr.getPassedCount());
        diff(out, "failedCount",     boxed(prev, QCResult::getFailedCount),    curr.getFailedCount());
        diff(out, "verifyCount",     boxed(prev, QCResult::getVerifyCount),    curr.getVerifyCount());
        diff(out, "manualPassCount", boxed(prev, QCResult::getManualPassCount), curr.getManualPassCount());
        diff(out, "totalRules",      boxed(prev, QCResult::getTotalRules),     curr.getTotalRules());
        diff(out, "subjectAddress",  prev != null ? prev.getSubjectAddress()  : null, curr.getSubjectAddress());
        diff(out, "reviewerNotes",   prev != null ? prev.getReviewerNotes()   : null, curr.getReviewerNotes());
        diff(out, "processedAt",     ts(prev != null ? prev.getProcessedAt()     : null), ts(curr.getProcessedAt()));
        diff(out, "reviewStartedAt", ts(prev != null ? prev.getReviewStartedAt() : null), ts(curr.getReviewStartedAt()));
        diff(out, "reviewedAt",      ts(prev != null ? prev.getReviewedAt()      : null), ts(curr.getReviewedAt()));
        diff(out, "supersededAt",    ts(prev != null ? prev.getSupersededAt()    : null), ts(curr.getSupersededAt()));

        return out;
    }

    private static void diff(Map<String, Object> out, String field, Object from, Object to) {
        if (!Objects.equals(from, to)) {
            Map<String, Object> change = new LinkedHashMap<>();
            change.put("from", from);
            change.put("to",   to);
            out.put(field, change);
        }
    }

    @FunctionalInterface
    private interface FieldGetter<T> { T get(QCResult r); }

    private static <T> T boxed(QCResult r, FieldGetter<T> getter) {
        return r != null ? getter.get(r) : null;
    }

    // ── Human-readable action label ────────────────────────────────────────────

    private static String summarizeAction(QCResult prev, QCResult curr, RevisionType revType) {
        if (revType == RevisionType.ADD) return "QC processing completed";
        if (revType == RevisionType.DEL) return "Record deleted";

        if (curr.getSupersededAt() != null && (prev == null || prev.getSupersededAt() == null))
            return "Superseded by rerun";
        if (curr.getFinalDecision() != null && (prev == null || prev.getFinalDecision() == null))
            return "Review submitted — " + curr.getFinalDecision().name().replace("_", " ").toLowerCase();
        if (curr.getReviewStartedAt() != null && (prev == null || prev.getReviewStartedAt() == null))
            return "Review session opened";
        if (curr.getReviewerNotes() != null
                && (prev == null || !curr.getReviewerNotes().equals(prev.getReviewerNotes())))
            return "Reviewer notes updated";
        if (!Objects.equals(curr.getPassedCount(), prev != null ? prev.getPassedCount() : null)
                || !Objects.equals(curr.getFailedCount(), prev != null ? prev.getFailedCount() : null))
            return "Rule counts updated";

        return "Modified";
    }

    private static String ts(LocalDateTime dt) {
        return dt != null ? dt.toString() : null;
    }
}
