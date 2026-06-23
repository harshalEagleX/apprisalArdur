package com.shal.controller.api;

import com.shal.common.entity.*;
import com.shal.common.repository.*;
import com.shal.common.service.EnversAuditService;
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
 * Performance model: every endpoint uses bulk IN-clause queries so the query
 * count is bounded and independent of the number of batches/files.
 *
 *   overview()      : 4 queries (batch page + files + active QCResults + mismatch set)
 *   batchSubgraph() : 4 queries (batch + files + active QCResults + mismatch set)
 *   fileSubgraph()  : 5 queries (file + all QC runs + mismatch set + audit logs + business events)
 *   reviewerGraph() : 4 queries (batches + files + active QCResults + mismatch set)
 *   search()        : 4 queries (batch page + files + active QCResults + mismatch set for matches)
 *
 * File history: fileSubgraph() exposes the full QC rerun chain via QC_RUN nodes.
 * When a file has been re-QC'd, each run gets its own QC_RUN node with a
 * SUPERSEDED_BY edge pointing to the next run (oldest → newest).
 */
@RestController
@RequestMapping("/api/graph")
@PreAuthorize("hasRole('ADMIN')")
@Transactional(readOnly = true)
public class AuditGraphController {

    private static final Logger log = LoggerFactory.getLogger(AuditGraphController.class);

    private final BatchRepository           batchRepository;
    private final BatchFileRepository       batchFileRepository;
    private final QCResultRepository        qcResultRepository;
    private final QCRuleResultRepository    qcRuleResultRepository;
    private final AuditLogRepository        auditLogRepository;
    private final BusinessEventRepository   businessEventRepository;
    private final EnversAuditService        enversAuditService;

    public AuditGraphController(
            BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            QCResultRepository qcResultRepository,
            QCRuleResultRepository qcRuleResultRepository,
            AuditLogRepository auditLogRepository,
            BusinessEventRepository businessEventRepository,
            EnversAuditService enversAuditService) {
        this.batchRepository         = batchRepository;
        this.batchFileRepository     = batchFileRepository;
        this.qcResultRepository      = qcResultRepository;
        this.qcRuleResultRepository  = qcRuleResultRepository;
        this.auditLogRepository      = auditLogRepository;
        this.businessEventRepository = businessEventRepository;
        this.enversAuditService      = enversAuditService;
    }

    // ── Overview: full graph ──────────────────────────────────────────────────

    @GetMapping("/overview")
    public ResponseEntity<Map<String, Object>> overview(
            @RequestParam(defaultValue = "0")  int page,
            @RequestParam(defaultValue = "50") int size) {

        var batches = batchRepository.findAll(
            PageRequest.of(page, Math.min(size, 100), Sort.by("createdAt").descending())
        ).getContent();

        log.info("[graph/overview] {} batches", batches.size());
        if (batches.isEmpty()) return ResponseEntity.ok(graph(List.of(), List.of()));

        List<Long> batchIds = batches.stream().map(Batch::getId).toList();

        // Three bulk queries replace N × (files + qcResults + mismatchCount)
        List<BatchFile> allFiles = batchFileRepository.findByBatchIdIn(batchIds);
        List<QCResult>  allQcrs  = qcResultRepository.findActiveByBatchIds(batchIds);
        Set<Long>        mismatch = mismatchSet(allQcrs.stream().map(QCResult::getId).toList());

        Map<Long, List<BatchFile>> filesByBatch = groupFilesByBatch(allFiles);
        Map<Long, QCResult>        qcByFileId   = indexQcrByFileId(allQcrs);

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        for (Batch b : batches) {
            nodes.add(batchNode(b));
            List<BatchFile> files    = filesByBatch.getOrDefault(b.getId(), List.of());
            Map<String, String> apprByOrder = appraisalNodeIdsByOrderId(files);
            String              soleAppr    = soleAppraisalNodeId(files);

            for (BatchFile file : files) {
                QCResult qcr = qcByFileId.get(file.getId());
                nodes.add(fileNode(file, qcr, b, mismatch));
                linkFileByRole(links, "batch_" + b.getId(), apprByOrder, soleAppr, file);
                if (qcr != null) appendSessionDecisionNodes(nodes, links, "file_" + file.getId(), qcr);
                if (nodes.size() >= 300) break;
            }
            if (nodes.size() >= 300) { log.info("[graph/overview] node cap reached"); break; }
        }

        log.info("[graph/overview] {} nodes, {} links", nodes.size(), links.size());
        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Batch subgraph ────────────────────────────────────────────────────────

    @GetMapping("/batch/{batchId}")
    public ResponseEntity<Map<String, Object>> batchSubgraph(@PathVariable Long batchId) {
        var batchOpt = batchRepository.findByIdWithClient(batchId);
        if (batchOpt.isEmpty()) return ResponseEntity.notFound().build();
        Batch batch = batchOpt.get();

        List<Long> ids = List.of(batchId);
        List<BatchFile> files = batchFileRepository.findByBatchIdIn(ids);
        List<QCResult>  qcrs  = qcResultRepository.findActiveByBatchIds(ids);
        Set<Long> mismatch     = mismatchSet(qcrs.stream().map(QCResult::getId).toList());

        Map<Long, QCResult> qcByFileId = indexQcrByFileId(qcrs);

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        nodes.add(batchNode(batch));
        Map<String, String> apprByOrder = appraisalNodeIdsByOrderId(files);
        String              soleAppr    = soleAppraisalNodeId(files);

        for (BatchFile file : files) {
            QCResult qcr = qcByFileId.get(file.getId());
            nodes.add(fileNode(file, qcr, batch, mismatch));
            linkFileByRole(links, "batch_" + batchId, apprByOrder, soleAppr, file);
            if (qcr != null) appendSessionDecisionNodes(nodes, links, "file_" + file.getId(), qcr);
        }

        log.info("[graph/batch] {} → {} files, {} qcrs, {} nodes", batchId, files.size(), qcrs.size(), nodes.size());
        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── File subgraph: complete version history ───────────────────────────────

    @GetMapping("/file/{fileId}")
    public ResponseEntity<Map<String, Object>> fileSubgraph(@PathVariable Long fileId) {
        var fileOpt = batchFileRepository.findWithBatchAndReviewerById(fileId);
        if (fileOpt.isEmpty()) return ResponseEntity.notFound().build();

        BatchFile file  = fileOpt.get();
        Batch     batch = file.getBatch();

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        // All QC runs for this file, newest first
        List<QCResult> allRuns = qcResultRepository.findAllByBatchFileIdOrderByProcessedAtDesc(fileId);

        if (allRuns.isEmpty()) {
            // Supporting doc: show the appraisal it backs and that appraisal's full journey
            nodes.add(fileNode(file, null, batch, Set.of()));
            if (batch != null && file.getFileType() != FileType.APPRAISAL) {
                List<BatchFile> appraisals = batchFileRepository.findByBatchIdIn(List.of(batch.getId()))
                    .stream().filter(f -> f.getFileType() == FileType.APPRAISAL).toList();
                BatchFile appr = appraisals.stream()
                    .filter(f -> file.getOrderId() != null && file.getOrderId().equals(f.getOrderId()))
                    .findFirst().orElse(appraisals.isEmpty() ? null : appraisals.get(0));
                if (appr != null) {
                    QCResult apprQcr = qcResultRepository.findByBatchFileId(appr.getId()).orElse(null);
                    Set<Long> apprMismatch = apprQcr != null ? mismatchSet(List.of(apprQcr.getId())) : Set.of();
                    nodes.add(fileNode(appr, apprQcr, batch, apprMismatch));
                    links.add(link("file_" + fileId, "file_" + appr.getId(), "SUPPORTS", null));
                    if (apprQcr != null) {
                        List<AuditLog> logs = auditLogRepository.findByEntityTypeAndEntityIdIn(
                            "QCResult", List.of(apprQcr.getId()));
                        appendSessionFromLogs(nodes, links, "file_" + appr.getId(), apprQcr, logs);
                    }
                }
            }
            log.info("[graph/file] {} has no QCResult ({} nodes)", fileId, nodes.size());
            return ResponseEntity.ok(graph(nodes, links));
        }

        List<Long> runIds    = allRuns.stream().map(QCResult::getId).toList();
        Set<Long>  mismatch  = mismatchSet(runIds);
        QCResult   activeQcr = allRuns.get(0); // newest = active (supersededAt IS NULL)

        nodes.add(fileNode(file, activeQcr, batch, mismatch));

        if (allRuns.size() == 1) {
            // Single run — show session/decision directly under file node
            List<AuditLog> logs = auditLogRepository.findByEntityTypeAndEntityIdIn("QCResult", runIds);
            appendSessionFromLogs(nodes, links, "file_" + fileId, activeQcr, logs);
        } else {
            // Multiple runs: emit a QC_RUN node per version, oldest → newest
            List<QCResult> runsAsc = new ArrayList<>(allRuns);
            Collections.reverse(runsAsc);

            // One batch query for ALL audit logs across all runs
            List<AuditLog> allLogs = auditLogRepository.findByEntityTypeAndEntityIdIn("QCResult", runIds);
            Map<Long, List<AuditLog>> logsByRun = allLogs.stream()
                .filter(al -> "REVIEW_SESSION_STARTED".equals(al.getAction()))
                .collect(Collectors.groupingBy(AuditLog::getEntityId));

            // One batch query for BusinessEvents keyed by QC run — lifecycle timestamps
            List<BusinessEvent> allEvents = businessEventRepository.findByQcResultIdIn(runIds);
            Map<Long, List<BusinessEvent>> eventsByRun = allEvents.stream()
                .collect(Collectors.groupingBy(BusinessEvent::getQcResultId));

            String prevId = "file_" + fileId;
            for (int i = 0; i < runsAsc.size(); i++) {
                QCResult run      = runsAsc.get(i);
                boolean  isActive = run.getSupersededAt() == null;
                String   runId    = "qcrun_" + run.getId();

                List<BusinessEvent> runEvents = eventsByRun.getOrDefault(run.getId(), List.of());
                nodes.add(qcRunNode(run, i + 1, isActive, mismatch, runEvents));
                links.add(link(prevId, runId, i == 0 ? "HAS_QC_RUN" : "SUPERSEDED_BY",
                               ts(run.getProcessedAt())));
                prevId = runId;

                List<AuditLog> runLogs = logsByRun.getOrDefault(run.getId(), List.of());
                appendSessionFromLogs(nodes, links, runId, run, runLogs);
            }
        }

        log.info("[graph/file] {} → {} runs, {} nodes", fileId, allRuns.size(), nodes.size());
        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Reviewer subgraph ─────────────────────────────────────────────────────

    @GetMapping("/reviewer/{userId}")
    public ResponseEntity<Map<String, Object>> reviewerGraph(@PathVariable Long userId) {
        List<Batch> batches = batchRepository.findByAssignedReviewerId(userId);
        log.info("[graph/reviewer] userId={} → {} batches", userId, batches.size());
        if (batches.isEmpty()) return ResponseEntity.ok(graph(List.of(), List.of()));

        List<Long> batchIds = batches.stream().map(Batch::getId).toList();
        List<BatchFile> allFiles = batchFileRepository.findByBatchIdIn(batchIds);
        List<QCResult>  allQcrs  = qcResultRepository.findActiveByBatchIds(batchIds);
        Set<Long>        mismatch = mismatchSet(allQcrs.stream().map(QCResult::getId).toList());

        Map<Long, List<BatchFile>> filesByBatch = groupFilesByBatch(allFiles);
        Map<Long, QCResult>        qcByFileId   = indexQcrByFileId(allQcrs);

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();
        Set<String> seen = new HashSet<>();

        for (Batch batch : batches) {
            String bNodeId = "batch_" + batch.getId();
            if (seen.add(bNodeId)) nodes.add(batchNode(batch));

            List<BatchFile> files    = filesByBatch.getOrDefault(batch.getId(), List.of());
            Map<String, String> apprByOrder = appraisalNodeIdsByOrderId(files);
            String              soleAppr    = soleAppraisalNodeId(files);

            for (BatchFile file : files) {
                String   fNodeId = "file_" + file.getId();
                QCResult qcr     = qcByFileId.get(file.getId());
                if (seen.add(fNodeId)) nodes.add(fileNode(file, qcr, batch, mismatch));
                linkFileByRole(links, bNodeId, apprByOrder, soleAppr, file);
                if (qcr != null) appendSessionDecisionNodes(nodes, links, fNodeId, qcr);
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

        // findAll uses @EntityGraph(client, assignedReviewer) — no LAZY on batch fields
        var allBatches = batchRepository.findAll(
            PageRequest.of(0, 200, Sort.by("createdAt").descending())
        ).getContent();

        if (allBatches.isEmpty()) return ResponseEntity.ok(graph(List.of(), List.of()));

        List<Long> allBatchIds = allBatches.stream().map(Batch::getId).toList();

        // Bulk-load files and active QCResults for ALL candidates — 2 queries
        List<BatchFile> allFiles = batchFileRepository.findByBatchIdIn(allBatchIds);
        List<QCResult>  allQcrs  = qcResultRepository.findActiveByBatchIds(allBatchIds);

        // Build lookup maps (no DB hits)
        Map<Long, List<BatchFile>> filesByBatch = groupFilesByBatch(allFiles);
        Map<Long, QCResult>        qcByFileId   = indexQcrByFileId(allQcrs);
        Map<Long, List<QCResult>>  qcrsByBatch  = groupQcrsByBatch(allQcrs, filesByBatch);

        // In-memory filter
        String      qLow       = q != null && !q.isBlank() ? q.toLowerCase() : null;
        BatchStatus statusEnum = parseStatus(status);

        List<Batch> matched = allBatches.stream().filter(b -> {
            if (client   != null && (b.getClient()           == null || !client.equals(b.getClient().getId())))           return false;
            if (reviewer != null && (b.getAssignedReviewer() == null || !reviewer.equals(b.getAssignedReviewer().getId()))) return false;
            if (statusEnum != null && b.getStatus() != statusEnum) return false;
            if (qLow == null) return true;

            if (b.getParentBatchId() != null && b.getParentBatchId().toLowerCase().contains(qLow)) return true;
            if (b.getClient() != null && b.getClient().getName() != null && b.getClient().getName().toLowerCase().contains(qLow)) return true;
            if (b.getAssignedReviewer() != null && b.getAssignedReviewer().getUsername() != null
                    && b.getAssignedReviewer().getUsername().toLowerCase().contains(qLow)) return true;

            List<BatchFile> bFiles = filesByBatch.getOrDefault(b.getId(), List.of());
            if (bFiles.stream().anyMatch(f ->
                (f.getFilename() != null && f.getFilename().toLowerCase().contains(qLow)) ||
                (f.getOrderId()  != null && f.getOrderId().toLowerCase().contains(qLow)))) return true;

            return qcrsByBatch.getOrDefault(b.getId(), List.of()).stream()
                .anyMatch(r -> r.getSubjectAddress() != null && r.getSubjectAddress().toLowerCase().contains(qLow));
        }).toList();

        if (matched.isEmpty()) {
            log.info("[graph/search] q='{}' status='{}' → 0 matches", q, status);
            return ResponseEntity.ok(graph(List.of(), List.of()));
        }

        // Mismatch set only for the matched subset
        List<Long> matchedQcrIds = matched.stream()
            .flatMap(b -> qcrsByBatch.getOrDefault(b.getId(), List.of()).stream().map(QCResult::getId))
            .toList();
        Set<Long> mismatch = mismatchSet(matchedQcrIds);

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();
        Set<String> seen = new HashSet<>();

        for (Batch b : matched) {
            String bNodeId = "batch_" + b.getId();
            if (seen.add(bNodeId)) nodes.add(batchNode(b));

            List<BatchFile> files    = filesByBatch.getOrDefault(b.getId(), List.of());
            Map<String, String> apprByOrder = appraisalNodeIdsByOrderId(files);
            String              soleAppr    = soleAppraisalNodeId(files);

            for (BatchFile file : files) {
                String   fNodeId = "file_" + file.getId();
                QCResult qcr     = qcByFileId.get(file.getId());
                if (seen.add(fNodeId)) nodes.add(fileNode(file, qcr, b, mismatch));
                linkFileByRole(links, bNodeId, apprByOrder, soleAppr, file);
                if (qcr != null) appendSessionDecisionNodes(nodes, links, fNodeId, qcr);
                if (nodes.size() >= 300) break;
            }
            if (nodes.size() >= 300) break;
        }

        log.info("[graph/search] q='{}' status='{}' → {} matched, {} nodes", q, status, matched.size(), nodes.size());
        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Envers revision history ───────────────────────────────────────────────

    /**
     * Returns the Envers field-level diff timeline for a single QCResult.
     * Powers the "Revision History" section in the audit graph's QC_RUN node drawer.
     * Each entry shows what changed, who changed it, the revision number, and timestamp.
     */
    @GetMapping("/revisions/qcresult/{qcResultId}")
    public ResponseEntity<List<Map<String, Object>>> qcResultRevisions(
            @PathVariable Long qcResultId) {
        return ResponseEntity.ok(enversAuditService.getQCResultRevisions(qcResultId));
    }

    // ── Session/decision builder — abbreviated (no audit log query) ───────────

    /**
     * Appends REVIEW_SESSION, DECISION, and SUBMIT nodes from QCResult embedded
     * fields only (no additional DB queries). Used for overview, batch, search,
     * and reviewer graph views where one session node per file is sufficient.
     */
    private void appendSessionDecisionNodes(
            List<Map<String, Object>> nodes,
            List<Map<String, Object>> links,
            String parentNodeId,
            QCResult qcr) {

        String lastNodeId = parentNodeId;

        if (qcr.getReviewStartedAt() != null) {
            String sessionId = "session_qcr_" + qcr.getId();
            User reviewer = qcr.getReviewLockedBy() != null ? qcr.getReviewLockedBy() : qcr.getReviewedBy();

            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("reviewer",      reviewer != null ? reviewer.getUsername() : null);
            meta.put("reviewerEmail", reviewer != null ? reviewer.getEmail()    : null);
            meta.put("startedAt",     ts(qcr.getReviewStartedAt()));
            meta.put("lastActiveAt",  ts(qcr.getReviewLastActiveAt()));
            meta.put("qcResultId",    qcr.getId());
            meta.put("qcDecision",    qcr.getQcDecision() != null ? qcr.getQcDecision().name() : null);

            String sessionStatus = qcr.getFinalDecision() != null ? "COMPLETED" : "ACTIVE";
            nodes.add(node(sessionId, "Review Session", "REVIEW_SESSION", sessionStatus, meta));
            links.add(link(parentNodeId, sessionId, "HAS_SESSION", ts(qcr.getReviewStartedAt())));
            lastNodeId = sessionId;
        }

        if (qcr.getFinalDecision() != null) {
            lastNodeId = appendDecisionAndSubmit(nodes, links, lastNodeId, qcr);
        }
    }

    // ── Session/decision builder — full detail (pre-fetched audit logs) ────────

    /**
     * Appends session/decision/submit nodes using pre-fetched audit logs.
     * The caller bulk-queries all logs for multiple QCResults at once and passes
     * each run's slice here — so this method never hits the DB.
     */
    private void appendSessionFromLogs(
            List<Map<String, Object>> nodes,
            List<Map<String, Object>> links,
            String parentNodeId,
            QCResult qcr,
            List<AuditLog> allLogsForQcr) {

        List<AuditLog> sessionLogs = allLogsForQcr.stream()
            .filter(al -> "REVIEW_SESSION_STARTED".equals(al.getAction()))
            .sorted(Comparator.comparing(al -> al.getCreatedAt() != null ? al.getCreatedAt() : LocalDateTime.MIN))
            .collect(Collectors.toList());

        String lastNodeId    = parentNodeId;
        int    sessionCount  = 0;

        for (AuditLog al : sessionLogs) {
            sessionCount++;
            String sessionId = "session_log_" + al.getId();
            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("reviewer",      al.getUser() != null ? al.getUser().getUsername() : "system");
            meta.put("reviewerEmail", al.getUser() != null ? al.getUser().getEmail()    : null);
            meta.put("startedAt",     ts(al.getCreatedAt()));
            meta.put("sessionIndex",  sessionCount);
            meta.put("qcResultId",    qcr.getId());

            nodes.add(node(sessionId, "Session #" + sessionCount, "REVIEW_SESSION", "ACTIVE", meta));
            String edgeType = sessionCount == 1 ? "HAS_SESSION" : "RE_REVIEW";
            links.add(link(lastNodeId, sessionId, edgeType, ts(al.getCreatedAt())));
            lastNodeId = sessionId;
        }

        // Fallback: synthesise one session from QCResult fields when no audit logs exist
        if (sessionCount == 0 && qcr.getReviewStartedAt() != null) {
            String sessionId = "session_qcr_" + qcr.getId();
            User   reviewer  = qcr.getReviewLockedBy() != null ? qcr.getReviewLockedBy() : qcr.getReviewedBy();
            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("reviewer",      reviewer != null ? reviewer.getUsername() : null);
            meta.put("reviewerEmail", reviewer != null ? reviewer.getEmail()    : null);
            meta.put("startedAt",     ts(qcr.getReviewStartedAt()));
            meta.put("lastActiveAt",  ts(qcr.getReviewLastActiveAt()));
            meta.put("qcResultId",    qcr.getId());
            meta.put("qcDecision",    qcr.getQcDecision() != null ? qcr.getQcDecision().name() : null);
            String sessionStatus = qcr.getFinalDecision() != null ? "COMPLETED" : "ACTIVE";
            nodes.add(node(sessionId, "Review Session", "REVIEW_SESSION", sessionStatus, meta));
            links.add(link(parentNodeId, sessionId, "HAS_SESSION", ts(qcr.getReviewStartedAt())));
            lastNodeId = sessionId;
        }

        if (qcr.getFinalDecision() != null) {
            appendDecisionAndSubmit(nodes, links, lastNodeId, qcr);
        }
    }

    // ── Decision + submit node helper ─────────────────────────────────────────

    private String appendDecisionAndSubmit(
            List<Map<String, Object>> nodes,
            List<Map<String, Object>> links,
            String sourceNodeId,
            QCResult qcr) {

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

        nodes.add(node(decisionId, "Decision: " + qcr.getFinalDecision().name(),
            "DECISION", qcr.getFinalDecision().name(), meta));
        links.add(link(sourceNodeId, decisionId, "RESULTED_IN", ts(qcr.getReviewedAt())));

        String submitId = "submit_qcr_" + qcr.getId();
        Map<String, Object> sMeta = new LinkedHashMap<>();
        sMeta.put("submittedAt",   ts(qcr.getReviewedAt()));
        sMeta.put("submittedBy",   qcr.getReviewedBy() != null ? qcr.getReviewedBy().getUsername() : null);
        sMeta.put("finalDecision", qcr.getFinalDecision().name());
        nodes.add(node(submitId, "Submitted", "SUBMIT", "DONE", sMeta));
        links.add(link(decisionId, submitId, "LED_TO", ts(qcr.getReviewedAt())));
        return decisionId;
    }

    // ── Node builders ─────────────────────────────────────────────────────────

    private Map<String, Object> batchNode(Batch b) {
        Client client   = b.getClient();
        User   reviewer = b.getAssignedReviewer();

        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("status",        b.getStatus() != null ? b.getStatus().name() : null);
        meta.put("client",        client   != null ? client.getName()        : null);
        meta.put("clientCode",    client   != null ? client.getCode()        : null);
        meta.put("reviewer",      reviewer != null ? reviewer.getUsername()  : null);
        meta.put("reviewerEmail", reviewer != null ? reviewer.getEmail()     : null);
        meta.put("fileCount",     b.getFileCount());
        meta.put("createdAt",     ts(b.getCreatedAt()));
        meta.put("updatedAt",     ts(b.getUpdatedAt()));

        return node(
            "batch_" + b.getId(),
            b.getParentBatchId() != null ? b.getParentBatchId() : "Batch #" + b.getId(),
            "BATCH",
            b.getStatus() != null ? b.getStatus().name() : "UNKNOWN",
            meta);
    }

    private Map<String, Object> fileNode(BatchFile file, QCResult qcr, Batch batch,
                                         Set<Long> mismatchIds) {
        Client client   = batch != null ? batch.getClient()           : null;
        User   reviewer = batch != null ? batch.getAssignedReviewer() : null;

        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("batchId",      batch    != null ? batch.getId()            : null);
        meta.put("batchName",    batch    != null ? batch.getParentBatchId() : null);
        meta.put("client",       client   != null ? client.getName()         : null);
        meta.put("reviewer",     reviewer != null ? reviewer.getUsername()   : null);
        meta.put("fileType",     file.getFileType() != null ? file.getFileType().name() : null);
        meta.put("orderId",      file.getOrderId());
        meta.put("uploadedAt",   ts(file.getCreatedAt()));
        meta.put("lastActionAt", ts(file.getUpdatedAt()));

        if (qcr != null) {
            meta.put("subjectAddress", qcr.getSubjectAddress());
            meta.put("addressMatch",   mismatchIds.contains(qcr.getId()) ? "MISMATCH" : "OK");
            meta.put("qcDecision",     qcr.getQcDecision()   != null ? qcr.getQcDecision().name()   : null);
            meta.put("finalDecision",  qcr.getFinalDecision() != null ? qcr.getFinalDecision().name() : null);
            meta.put("qcReviewer",     qcr.getReviewedBy()   != null ? qcr.getReviewedBy().getUsername() : null);
            meta.put("passedRules",    qcr.getPassedCount());
            meta.put("failedRules",    qcr.getFailedCount());
            meta.put("totalRules",     qcr.getTotalRules());
            meta.put("reviewedAt",     ts(qcr.getReviewedAt()));
        }

        return node(
            "file_" + file.getId(),
            file.getFilename() != null ? file.getFilename() : "File #" + file.getId(),
            "FILE",
            file.getStatus() != null ? file.getStatus().name() : "UNKNOWN",
            meta);
    }

    private Map<String, Object> qcRunNode(QCResult run, int runNumber, boolean isActive,
                                          Set<Long> mismatchIds) {
        return qcRunNode(run, runNumber, isActive, mismatchIds, List.of());
    }

    private Map<String, Object> qcRunNode(QCResult run, int runNumber, boolean isActive,
                                          Set<Long> mismatchIds, List<BusinessEvent> events) {
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("qcResultId",    run.getId());
        meta.put("runNumber",     runNumber);
        meta.put("processedAt",   ts(run.getProcessedAt()));
        meta.put("qcDecision",    run.getQcDecision()   != null ? run.getQcDecision().name()   : null);
        meta.put("finalDecision", run.getFinalDecision() != null ? run.getFinalDecision().name() : null);
        meta.put("passedRules",   run.getPassedCount());
        meta.put("failedRules",   run.getFailedCount());
        meta.put("totalRules",    run.getTotalRules());
        meta.put("addressMatch",  mismatchIds.contains(run.getId()) ? "MISMATCH" : "OK");
        meta.put("supersededAt",  ts(run.getSupersededAt()));

        // QC engine lifecycle timestamps from BusinessEvent (non-null only when events exist)
        for (BusinessEvent ev : events) {
            switch (ev.getEventType()) {
                case "BATCH_QC_STARTED"      -> meta.putIfAbsent("qcStartedAt",   ts(ev.getOccurredAt()));
                case "BATCH_QC_COMPLETED"    -> meta.putIfAbsent("qcCompletedAt", ts(ev.getOccurredAt()));
                case "QC_RESULT_SUPERSEDED"  -> meta.putIfAbsent("supersededEvent", ev.getPayloadJson());
            }
        }

        return node(
            "qcrun_" + run.getId(),
            "QC Run #" + runNumber + (isActive ? " (Active)" : " (Superseded)"),
            "QC_RUN",
            isActive ? "ACTIVE" : "SUPERSEDED",
            meta);
    }

    // ── Grouping helpers ──────────────────────────────────────────────────────

    /** Group files by batch.id (batch is JOIN FETCHed in findByBatchIdIn). */
    private static Map<Long, List<BatchFile>> groupFilesByBatch(List<BatchFile> files) {
        return files.stream().collect(Collectors.groupingBy(f -> f.getBatch().getId()));
    }

    /** Index the active QCResult per file. Active-only guaranteed by findActiveByBatchIds. */
    private static Map<Long, QCResult> indexQcrByFileId(List<QCResult> qcrs) {
        Map<Long, QCResult> map = new HashMap<>();
        for (QCResult qcr : qcrs) {
            if (qcr.getBatchFile() != null) map.put(qcr.getBatchFile().getId(), qcr);
        }
        return map;
    }

    /**
     * Group QCResults by batch ID without touching qcr.batchFile.batch (LAZY).
     * Uses the pre-built file → batch map instead.
     */
    private static Map<Long, List<QCResult>> groupQcrsByBatch(
            List<QCResult> qcrs, Map<Long, List<BatchFile>> filesByBatch) {
        // Invert filesByBatch to fileId → batchId
        Map<Long, Long> batchByFileId = new HashMap<>();
        for (Map.Entry<Long, List<BatchFile>> e : filesByBatch.entrySet()) {
            for (BatchFile f : e.getValue()) batchByFileId.put(f.getId(), e.getKey());
        }
        Map<Long, List<QCResult>> out = new HashMap<>();
        for (QCResult qcr : qcrs) {
            if (qcr.getBatchFile() == null) continue;
            Long batchId = batchByFileId.get(qcr.getBatchFile().getId());
            if (batchId != null) out.computeIfAbsent(batchId, k -> new ArrayList<>()).add(qcr);
        }
        return out;
    }

    // ── Mismatch helper ───────────────────────────────────────────────────────

    private Set<Long> mismatchSet(List<Long> qcrIds) {
        if (qcrIds.isEmpty()) return Set.of();
        return new HashSet<>(qcRuleResultRepository.findQcResultIdsWithAddressMismatch(qcrIds));
    }

    // ── Link / graph helpers ──────────────────────────────────────────────────

    /**
     * Build the appraisal-to-orderId lookup and the sole-appraisal shortcut used
     * by linkFileByRole.
     */
    private static Map<String, String> appraisalNodeIdsByOrderId(List<BatchFile> files) {
        Map<String, String> byOrder = new HashMap<>();
        for (BatchFile f : files) {
            if (f.getFileType() == FileType.APPRAISAL
                    && f.getOrderId() != null && !f.getOrderId().isBlank()) {
                byOrder.putIfAbsent(f.getOrderId(), "file_" + f.getId());
            }
        }
        return byOrder;
    }

    private static String soleAppraisalNodeId(List<BatchFile> files) {
        List<BatchFile> appr = files.stream()
            .filter(f -> f.getFileType() == FileType.APPRAISAL).toList();
        return appr.size() == 1 ? "file_" + appr.get(0).getId() : null;
    }

    private void linkFileByRole(List<Map<String, Object>> links, String batchNodeId,
                                Map<String, String> apprByOrder, String soleAppr,
                                BatchFile file) {
        String fileNodeId = "file_" + file.getId();
        if (file.getFileType() == FileType.APPRAISAL) {
            links.add(link(batchNodeId, fileNodeId, "CONTAINS", null));
            return;
        }
        String anchor = file.getOrderId() != null ? apprByOrder.get(file.getOrderId()) : null;
        if (anchor == null) anchor = soleAppr;
        if (anchor != null && !anchor.equals(fileNodeId)) {
            links.add(link(fileNodeId, anchor, "SUPPORTS", null));
        } else {
            links.add(link(batchNodeId, fileNodeId, "CONTAINS", null));
        }
    }

    // ── Primitive builders ────────────────────────────────────────────────────

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

    private static BatchStatus parseStatus(String status) {
        if (status == null || status.isBlank()) return null;
        try { return BatchStatus.valueOf(status.toUpperCase()); }
        catch (IllegalArgumentException ignored) { return null; }
    }
}
