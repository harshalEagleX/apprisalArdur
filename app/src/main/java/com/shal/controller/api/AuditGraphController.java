package com.shal.controller.api;

import com.shal.common.entity.*;
import com.shal.common.repository.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Graph API for the Audit Intelligence Graph view.
 *
 * Data model reality (confirmed from DB):
 *   - Sessions are tracked on QCResult (review_started_at, review_locked_by)
 *     AND logged in audit_log as REVIEW_SESSION_STARTED (entityType=QCResult)
 *   - Decisions are tracked on QCResult.final_decision (set by VerificationService)
 *     No "REVIEW_SUBMITTED" audit log exists — only the QCResult field is authoritative
 *   - Multiple REVIEW_SESSION_STARTED logs for the same QCResult = re-entered sessions
 *   - REVIEW_DECISION_SAVED logs exist per QCRuleResult (not shown — too granular)
 *
 * @Transactional(readOnly = true) keeps the Hibernate session open so all
 * LAZY associations (client, assignedReviewer, batchFile, reviewedBy, reviewLockedBy)
 * resolve without LazyInitializationException.
 */
@RestController
@RequestMapping("/api/graph")
@PreAuthorize("hasRole('ADMIN')")
@Transactional(readOnly = true)
public class AuditGraphController {

    private static final Logger log = LoggerFactory.getLogger(AuditGraphController.class);

    private final BatchRepository     batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final QCResultRepository  qcResultRepository;
    private final AuditLogRepository  auditLogRepository;

    public AuditGraphController(
            BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            QCResultRepository qcResultRepository,
            AuditLogRepository auditLogRepository) {
        this.batchRepository     = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.qcResultRepository  = qcResultRepository;
        this.auditLogRepository  = auditLogRepository;
    }

    // ── Overview: full graph — batches → files → sessions → decisions ─────────

    @GetMapping("/overview")
    public ResponseEntity<Map<String, Object>> overview(
            @RequestParam(defaultValue = "0")   int page,
            @RequestParam(defaultValue = "50")  int size) {

        var batches = batchRepository.findAll(
            PageRequest.of(page, Math.min(size, 100), Sort.by("createdAt").descending())
        ).getContent();

        log.info("[graph/overview] {} batches", batches.size());

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        for (Batch b : batches) {
            nodes.add(batchNode(b));

            List<BatchFile> files  = batchFileRepository.findByBatchId(b.getId());
            List<QCResult>  qcrs   = qcResultRepository.findByBatchId(b.getId());
            Map<Long, QCResult> qcByFileId = buildQcByFileId(qcrs);

            log.info("[graph/overview] batch {} → {} files, {} qcResults",
                b.getId(), files.size(), qcrs.size());

            for (BatchFile file : files) {
                QCResult qcr = qcByFileId.get(file.getId());
                nodes.add(fileNode(file, qcr, b));
                links.add(link("batch_" + b.getId(), "file_" + file.getId(), "CONTAINS", null));

                if (qcr != null) {
                    appendSessionDecisionNodes(nodes, links, "file_" + file.getId(), qcr, false);
                }
                if (nodes.size() >= 300) break;
            }
            if (nodes.size() >= 300) {
                log.info("[graph/overview] node cap (300) reached");
                break;
            }
        }

        log.info("[graph/overview] returning {} nodes, {} links", nodes.size(), links.size());
        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Batch subgraph: batch + files + sessions + decisions ─────────────────

    @GetMapping("/batch/{batchId}")
    public ResponseEntity<Map<String, Object>> batchSubgraph(@PathVariable Long batchId) {
        var batchOpt = batchRepository.findById(batchId);
        if (batchOpt.isEmpty()) {
            log.warn("[graph/batch] {} not found", batchId);
            return ResponseEntity.notFound().build();
        }
        Batch batch = batchOpt.get();
        log.info("[graph/batch] id={} status={} client={}", batchId, batch.getStatus(),
            batch.getClient() != null ? batch.getClient().getName() : "none");

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        nodes.add(batchNode(batch));

        List<BatchFile> files = batchFileRepository.findByBatchId(batchId);
        List<QCResult>  qcrs  = qcResultRepository.findByBatchId(batchId);
        Map<Long, QCResult> qcByFileId = buildQcByFileId(qcrs);

        log.info("[graph/batch] {} → {} files, {} qcResults", batchId, files.size(), qcrs.size());

        for (BatchFile file : files) {
            QCResult qcr = qcByFileId.get(file.getId());
            nodes.add(fileNode(file, qcr, batch));
            links.add(link("batch_" + batchId, "file_" + file.getId(), "CONTAINS", null));

            if (qcr != null) {
                appendSessionDecisionNodes(nodes, links, "file_" + file.getId(), qcr, false);
            }
        }

        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── File subgraph: complete journey for one file ──────────────────────────

    @GetMapping("/file/{fileId}")
    public ResponseEntity<Map<String, Object>> fileSubgraph(@PathVariable Long fileId) {
        var fileOpt = batchFileRepository.findById(fileId);
        if (fileOpt.isEmpty()) {
            log.warn("[graph/file] {} not found", fileId);
            return ResponseEntity.notFound().build();
        }
        BatchFile file  = fileOpt.get();
        Batch     batch = file.getBatch();
        log.info("[graph/file] id={} name={} batch={}", fileId, file.getFilename(),
            batch != null ? batch.getId() : "none");

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        var qcOpt = qcResultRepository.findByBatchFileId(fileId);
        QCResult qcr = qcOpt.orElse(null);

        nodes.add(fileNode(file, qcr, batch));

        if (qcr == null) {
            log.info("[graph/file] {} has no QCResult", fileId);
            return ResponseEntity.ok(graph(nodes, links));
        }

        log.info("[graph/file] qcr={} decision={} final={} startedAt={} reviewedAt={}",
            qcr.getId(), qcr.getQcDecision(), qcr.getFinalDecision(),
            qcr.getReviewStartedAt(), qcr.getReviewedAt());

        // Full detail: use audit logs to show distinct session entries
        appendSessionDecisionNodes(nodes, links, "file_" + fileId, qcr, true);

        log.info("[graph/file] {} → {} nodes, {} links", fileId, nodes.size(), links.size());
        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Reviewer subgraph ─────────────────────────────────────────────────────

    @GetMapping("/reviewer/{userId}")
    public ResponseEntity<Map<String, Object>> reviewerGraph(@PathVariable Long userId) {
        List<Batch> batches = batchRepository.findByAssignedReviewerId(userId);
        log.info("[graph/reviewer] userId={} → {} batches", userId, batches.size());

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();
        Set<String> seen = new HashSet<>();

        for (Batch batch : batches) {
            String batchNodeId = "batch_" + batch.getId();
            if (seen.add(batchNodeId)) nodes.add(batchNode(batch));

            List<BatchFile> files = batchFileRepository.findByBatchId(batch.getId());
            List<QCResult>  qcrs  = qcResultRepository.findByBatchId(batch.getId());
            Map<Long, QCResult> qcByFileId = buildQcByFileId(qcrs);

            for (BatchFile file : files) {
                String fileNodeId = "file_" + file.getId();
                QCResult qcr = qcByFileId.get(file.getId());
                if (seen.add(fileNodeId)) nodes.add(fileNode(file, qcr, batch));
                links.add(link(batchNodeId, fileNodeId, "CONTAINS", null));
                if (qcr != null) appendSessionDecisionNodes(nodes, links, fileNodeId, qcr, false);
            }
        }

        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Search ────────────────────────────────────────────────────────────────

    @GetMapping("/search")
    public ResponseEntity<Map<String, Object>> search(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) Long   reviewer,
            @RequestParam(required = false) Long   client) {

        var allBatches = batchRepository.findAll(
            PageRequest.of(0, 200, Sort.by("createdAt").descending())
        ).getContent();

        String qLow = q != null && !q.isBlank() ? q.toLowerCase() : null;
        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();
        Set<String> seen = new HashSet<>();

        for (Batch batch : allBatches) {
            if (client != null && (batch.getClient() == null || !client.equals(batch.getClient().getId()))) continue;
            if (reviewer != null && (batch.getAssignedReviewer() == null || !reviewer.equals(batch.getAssignedReviewer().getId()))) continue;
            if (status != null && !status.isBlank()) {
                try { if (batch.getStatus() != BatchStatus.valueOf(status.toUpperCase())) continue; }
                catch (IllegalArgumentException ignored) { continue; }
            }
            // Load files early so we can match on filename / orderId even when
            // the batch-level fields don't contain the search term.
            List<BatchFile> files        = batchFileRepository.findByBatchId(batch.getId());
            List<QCResult>  qcrs         = qcResultRepository.findByBatchId(batch.getId());
            Map<Long, QCResult> qcByFileId = buildQcByFileId(qcrs);

            if (qLow != null) {
                // Batch-level match: parentBatchId, client name, reviewer username
                boolean batchHit =
                    (batch.getParentBatchId() != null && batch.getParentBatchId().toLowerCase().contains(qLow)) ||
                    (batch.getClient() != null && batch.getClient().getName() != null && batch.getClient().getName().toLowerCase().contains(qLow)) ||
                    (batch.getAssignedReviewer() != null && batch.getAssignedReviewer().getUsername() != null && batch.getAssignedReviewer().getUsername().toLowerCase().contains(qLow));

                // File-level match: filename, orderId — include the batch if ANY file matches
                boolean fileHit = files.stream().anyMatch(f ->
                    (f.getFilename() != null && f.getFilename().toLowerCase().contains(qLow)) ||
                    (f.getOrderId()  != null && f.getOrderId().toLowerCase().contains(qLow))
                );

                if (!batchHit && !fileHit) continue;
            }

            String batchNodeId = "batch_" + batch.getId();
            if (seen.add(batchNodeId)) nodes.add(batchNode(batch));

            for (BatchFile file : files) {
                String fileNodeId = "file_" + file.getId();
                QCResult qcr = qcByFileId.get(file.getId());
                if (seen.add(fileNodeId)) nodes.add(fileNode(file, qcr, batch));
                links.add(link(batchNodeId, fileNodeId, "CONTAINS", null));
                if (qcr != null) appendSessionDecisionNodes(nodes, links, fileNodeId, qcr, false);
                if (nodes.size() >= 300) break;
            }
            if (nodes.size() >= 300) break;
        }

        log.info("[graph/search] q='{}' status='{}' → {} nodes, {} links", q, status, nodes.size(), links.size());
        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Core graph builder — session / decision / submit nodes ───────────────

    /**
     * Appends REVIEW_SESSION, DECISION, and SUBMIT nodes for a given QCResult.
     *
     * Strategy (from confirmed data model):
     *   1. Fetch audit logs with action=REVIEW_SESSION_STARTED for this QCResult.
     *      Multiple logs = reviewer re-entered the session (treated as re-review).
     *   2. If no audit logs exist but QCResult.reviewStartedAt is set,
     *      synthesise one session node directly from the QCResult fields.
     *   3. DECISION + SUBMIT come exclusively from QCResult.finalDecision
     *      (no "REVIEW_SUBMITTED" audit log is written by the system).
     *
     * @param useAuditLogs true for the file-journey view (full detail);
     *                     false for overview/batch views (one session per file)
     */
    private void appendSessionDecisionNodes(
            List<Map<String, Object>> nodes,
            List<Map<String, Object>> links,
            String fileNodeId,
            QCResult qcr,
            boolean useAuditLogs) {

        String lastSessionId = null;
        String prevNodeId    = fileNodeId;
        int    sessionCount  = 0;

        if (useAuditLogs) {
            // Full detail — build one node per REVIEW_SESSION_STARTED audit entry
            List<AuditLog> sessionLogs = auditLogRepository
                .findByEntityTypeAndEntityId("QCResult", qcr.getId())
                .stream()
                .filter(al -> "REVIEW_SESSION_STARTED".equals(al.getAction()))
                .sorted(Comparator.comparing(al -> al.getCreatedAt() != null ? al.getCreatedAt() : LocalDateTime.MIN))
                .collect(Collectors.toList());

            log.debug("[appendSession] qcr={} auditLogs={}", qcr.getId(), sessionLogs.size());

            for (AuditLog al : sessionLogs) {
                sessionCount++;
                String sessionId = "session_log_" + al.getId();
                lastSessionId = sessionId;

                Map<String, Object> meta = new LinkedHashMap<>();
                meta.put("reviewer",      al.getUser() != null ? al.getUser().getUsername()  : "system");
                meta.put("reviewerEmail", al.getUser() != null ? al.getUser().getEmail()      : null);
                meta.put("startedAt",     ts(al.getCreatedAt()));
                meta.put("sessionIndex",  sessionCount);
                meta.put("qcResultId",    qcr.getId());

                nodes.add(node(sessionId, "Session #" + sessionCount,
                    "REVIEW_SESSION", "ACTIVE", meta));

                String edgeType = sessionCount == 1 ? "HAS_SESSION" : "RE_REVIEW";
                links.add(link(prevNodeId, sessionId, edgeType, ts(al.getCreatedAt())));
                prevNodeId = sessionId;
            }
        }

        // Fallback (overview/batch mode OR no audit logs found):
        // synthesise one session from QCResult embedded fields
        if (sessionCount == 0 && qcr.getReviewStartedAt() != null) {
            String sessionId = "session_qcr_" + qcr.getId();
            lastSessionId = sessionId;

            User reviewer = qcr.getReviewLockedBy() != null
                ? qcr.getReviewLockedBy()
                : qcr.getReviewedBy();

            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("reviewer",      reviewer != null ? reviewer.getUsername() : null);
            meta.put("reviewerEmail", reviewer != null ? reviewer.getEmail()    : null);
            meta.put("startedAt",     ts(qcr.getReviewStartedAt()));
            meta.put("lastActiveAt",  ts(qcr.getReviewLastActiveAt()));
            meta.put("qcResultId",    qcr.getId());
            meta.put("qcDecision",    qcr.getQcDecision() != null ? qcr.getQcDecision().name() : null);

            String sessionStatus = qcr.getFinalDecision() != null ? "COMPLETED" : "ACTIVE";
            nodes.add(node(sessionId, "Review Session", "REVIEW_SESSION", sessionStatus, meta));
            links.add(link(prevNodeId, sessionId, "HAS_SESSION", ts(qcr.getReviewStartedAt())));
        }

        // DECISION node — always from QCResult.finalDecision (never from audit log)
        if (qcr.getFinalDecision() != null) {
            String decisionId = "decision_qcr_" + qcr.getId();

            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("outcome",       qcr.getFinalDecision().name());
            meta.put("qcDecision",    qcr.getQcDecision() != null ? qcr.getQcDecision().name() : null);
            meta.put("reviewer",      qcr.getReviewedBy() != null ? qcr.getReviewedBy().getUsername() : null);
            meta.put("reviewerEmail", qcr.getReviewedBy() != null ? qcr.getReviewedBy().getEmail()    : null);
            meta.put("reviewedAt",    ts(qcr.getReviewedAt()));
            meta.put("notes",         qcr.getReviewerNotes());
            meta.put("passedRules",   qcr.getPassedCount());
            meta.put("failedRules",   qcr.getFailedCount());
            meta.put("verifyCount",   qcr.getVerifyCount());
            meta.put("manualPassed",  qcr.getManualPassCount());

            nodes.add(node(decisionId,
                "Decision: " + qcr.getFinalDecision().name(),
                "DECISION",
                qcr.getFinalDecision().name(),
                meta));

            String decisionSrc = lastSessionId != null ? lastSessionId : fileNodeId;
            links.add(link(decisionSrc, decisionId, "RESULTED_IN", ts(qcr.getReviewedAt())));

            // SUBMIT node
            String submitId = "submit_qcr_" + qcr.getId();
            Map<String, Object> sMeta = new LinkedHashMap<>();
            sMeta.put("submittedAt",   ts(qcr.getReviewedAt()));
            sMeta.put("submittedBy",   qcr.getReviewedBy() != null ? qcr.getReviewedBy().getUsername() : null);
            sMeta.put("finalDecision", qcr.getFinalDecision().name());

            nodes.add(node(submitId, "Submitted", "SUBMIT", "DONE", sMeta));
            links.add(link(decisionId, submitId, "LED_TO", ts(qcr.getReviewedAt())));

            log.debug("[appendSession] qcr={} decision={} submit added", qcr.getId(), qcr.getFinalDecision());
        }
    }

    // ── Node builders ─────────────────────────────────────────────────────────

    private Map<String, Object> batchNode(Batch b) {
        Client client   = b.getClient();
        User   reviewer = b.getAssignedReviewer();

        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("status",        b.getStatus() != null ? b.getStatus().name() : null);
        meta.put("client",        client   != null ? client.getName()            : null);
        meta.put("clientCode",    client   != null ? client.getCode()            : null);
        meta.put("reviewer",      reviewer != null ? reviewer.getUsername()      : null);
        meta.put("reviewerEmail", reviewer != null ? reviewer.getEmail()         : null);
        meta.put("fileCount",     b.getFileCount());
        meta.put("createdAt",     ts(b.getCreatedAt()));
        meta.put("updatedAt",     ts(b.getUpdatedAt()));

        return node(
            "batch_" + b.getId(),
            b.getParentBatchId() != null ? b.getParentBatchId() : "Batch #" + b.getId(),
            "BATCH",
            b.getStatus() != null ? b.getStatus().name() : "UNKNOWN",
            meta
        );
    }

    private Map<String, Object> fileNode(BatchFile file, QCResult qcr, Batch batch) {
        Client client   = batch != null ? batch.getClient()           : null;
        User   reviewer = batch != null ? batch.getAssignedReviewer() : null;

        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("batchId",       batch  != null ? batch.getId()            : null);
        meta.put("batchName",     batch  != null ? batch.getParentBatchId() : null);
        meta.put("client",        client != null ? client.getName()         : null);
        meta.put("reviewer",      reviewer != null ? reviewer.getUsername() : null);
        meta.put("fileType",      file.getFileType() != null ? file.getFileType().name()  : null);
        meta.put("orderId",       file.getOrderId());
        meta.put("uploadedAt",    ts(file.getCreatedAt()));
        meta.put("lastActionAt",  ts(file.getUpdatedAt()));

        if (qcr != null) {
            meta.put("qcDecision",   qcr.getQcDecision()   != null ? qcr.getQcDecision().name()   : null);
            meta.put("finalDecision",qcr.getFinalDecision() != null ? qcr.getFinalDecision().name(): null);
            meta.put("qcReviewer",   qcr.getReviewedBy()   != null ? qcr.getReviewedBy().getUsername() : null);
            meta.put("passedRules",  qcr.getPassedCount());
            meta.put("failedRules",  qcr.getFailedCount());
            meta.put("totalRules",   qcr.getTotalRules());
            meta.put("reviewedAt",   ts(qcr.getReviewedAt()));
        }

        return node(
            "file_" + file.getId(),
            file.getFilename() != null ? file.getFilename() : "File #" + file.getId(),
            "FILE",
            file.getStatus() != null ? file.getStatus().name() : "UNKNOWN",
            meta
        );
    }

    // ── Utilities ─────────────────────────────────────────────────────────────

    private static Map<Long, QCResult> buildQcByFileId(List<QCResult> qcrs) {
        Map<Long, QCResult> map = new HashMap<>();
        for (QCResult qcr : qcrs) {
            if (qcr.getBatchFile() != null) {
                map.put(qcr.getBatchFile().getId(), qcr);
            }
        }
        return map;
    }

    private static Map<String, Object> node(String id, String label, String type,
                                            String status, Map<String, Object> meta) {
        Map<String, Object> n = new LinkedHashMap<>();
        n.put("id",     id);
        n.put("label",  label);
        n.put("type",   type);
        n.put("status", status);
        n.put("meta",   meta != null ? meta : Map.of());
        return n;
    }

    private static Map<String, Object> link(String source, String target,
                                            String type, String timestamp) {
        Map<String, Object> l = new LinkedHashMap<>();
        l.put("source", source);
        l.put("target", target);
        l.put("type",   type);
        if (timestamp != null) l.put("timestamp", timestamp);
        return l;
    }

    private static Map<String, Object> graph(List<Map<String, Object>> nodes,
                                             List<Map<String, Object>> links) {
        Map<String, Object> g = new LinkedHashMap<>();
        g.put("nodes", nodes);
        g.put("links", links);
        return g;
    }

    private static String ts(LocalDateTime dt) {
        return dt != null ? dt.toString() : null;
    }
}
