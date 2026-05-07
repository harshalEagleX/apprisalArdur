package com.apprisal.controller.api;

import com.apprisal.common.entity.*;
import com.apprisal.common.repository.*;
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
 * @Transactional(readOnly = true) keeps the Hibernate session open for the
 * entire request so lazy associations (client, assignedReviewer, batchFile, etc.)
 * can be fetched without LazyInitializationException. Without it every lazy
 * access outside an explicit JOIN FETCH throws.
 *
 * Each endpoint returns { nodes: [...], links: [...] } shaped for force-graph.
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

    // ── Overview: all batches + their files (capped at 300 nodes) ─────────────

    @GetMapping("/overview")
    public ResponseEntity<Map<String, Object>> overview(
            @RequestParam(defaultValue = "0")   int page,
            @RequestParam(defaultValue = "100") int size) {

        var batches = batchRepository.findAll(
            PageRequest.of(page, Math.min(size, 100), Sort.by("createdAt").descending())
        ).getContent();

        log.info("[graph/overview] loaded {} batches", batches.size());

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        for (Batch b : batches) {
            nodes.add(batchNode(b));

            List<BatchFile> files = batchFileRepository.findByBatchId(b.getId());
            log.debug("[graph/overview] batch {} → {} files", b.getId(), files.size());

            for (BatchFile file : files) {
                nodes.add(fileNode(file, null, b));
                links.add(link("batch_" + b.getId(), "file_" + file.getId(), "CONTAINS", null));
                if (nodes.size() >= 300) break;
            }
            if (nodes.size() >= 300) {
                log.info("[graph/overview] node cap (300) reached — truncating");
                break;
            }
        }

        log.info("[graph/overview] returning {} nodes, {} links", nodes.size(), links.size());
        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Batch subgraph: batch + all file nodes + edges ────────────────────────

    @GetMapping("/batch/{batchId}")
    public ResponseEntity<Map<String, Object>> batchSubgraph(@PathVariable Long batchId) {
        var batchOpt = batchRepository.findById(batchId);
        if (batchOpt.isEmpty()) {
            log.warn("[graph/batch] batch {} not found", batchId);
            return ResponseEntity.notFound().build();
        }
        Batch batch = batchOpt.get();
        log.info("[graph/batch] batchId={} client={} status={}",
            batchId, safeStr(batch.getClient(), c -> c.getName()), batch.getStatus());

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        nodes.add(batchNode(batch));

        List<BatchFile> files = batchFileRepository.findByBatchId(batchId);
        List<QCResult>  qcrs  = qcResultRepository.findByBatchId(batchId);
        Map<Long, QCResult> qcByFileId = buildQcByFileId(qcrs);

        log.info("[graph/batch] batchId={} → {} files, {} qcResults", batchId, files.size(), qcrs.size());

        for (BatchFile file : files) {
            QCResult qcr = qcByFileId.get(file.getId());
            nodes.add(fileNode(file, qcr, batch));
            links.add(link("batch_" + batchId, "file_" + file.getId(), "CONTAINS", null));
        }

        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── File subgraph: complete audit journey for one file ────────────────────

    @GetMapping("/file/{fileId}")
    public ResponseEntity<Map<String, Object>> fileSubgraph(@PathVariable Long fileId) {
        var fileOpt = batchFileRepository.findById(fileId);
        if (fileOpt.isEmpty()) {
            log.warn("[graph/file] file {} not found", fileId);
            return ResponseEntity.notFound().build();
        }
        BatchFile file = fileOpt.get();
        Batch     batch = file.getBatch();
        log.info("[graph/file] fileId={} filename={} batchId={}",
            fileId, file.getFilename(), batch != null ? batch.getId() : null);

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        var qcOpt = qcResultRepository.findByBatchFileId(fileId);
        QCResult qcr = qcOpt.orElse(null);

        nodes.add(fileNode(file, qcr, batch));

        if (qcr == null) {
            log.info("[graph/file] fileId={} has no QCResult — returning file-only graph", fileId);
            return ResponseEntity.ok(graph(nodes, links));
        }

        log.info("[graph/file] qcResultId={} qcDecision={} finalDecision={} reviewedBy={}",
            qcr.getId(), qcr.getQcDecision(), qcr.getFinalDecision(),
            qcr.getReviewedBy() != null ? qcr.getReviewedBy().getUsername() : "none");

        // Build review sessions from REVIEW_SESSION_STARTED audit logs
        List<AuditLog> auditLogs = auditLogRepository.findByEntityTypeAndEntityId("QCResult", qcr.getId());
        auditLogs.sort(Comparator.comparing(al -> al.getCreatedAt() != null ? al.getCreatedAt() : LocalDateTime.MIN));

        log.info("[graph/file] qcResultId={} → {} audit log entries", qcr.getId(), auditLogs.size());

        String fileNodeId   = "file_" + fileId;
        String lastNodeId   = fileNodeId;
        String lastSessionId = null;
        int    sessionIdx   = 0;

        for (AuditLog al : auditLogs) {
            if (!"REVIEW_SESSION_STARTED".equals(al.getAction())) continue;

            sessionIdx++;
            String sessionNodeId = "session_" + al.getId();
            lastSessionId = sessionNodeId;

            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("reviewer",      al.getUser() != null ? al.getUser().getUsername() : "system");
            meta.put("reviewerEmail", al.getUser() != null ? al.getUser().getEmail()    : null);
            meta.put("startedAt",     ts(al.getCreatedAt()));
            meta.put("sessionIndex",  sessionIdx);

            nodes.add(node(sessionNodeId, "Session #" + sessionIdx, "REVIEW_SESSION", "ACTIVE", meta));

            String edgeType = sessionIdx == 1 ? "HAS_SESSION" : "RE_REVIEW";
            links.add(link(lastNodeId, sessionNodeId, edgeType, ts(al.getCreatedAt())));
            lastNodeId = sessionNodeId;

            log.debug("[graph/file] session #{} by {} at {}", sessionIdx,
                meta.get("reviewer"), meta.get("startedAt"));
        }

        // DECISION node from QCResult.finalDecision
        if (qcr.getFinalDecision() != null) {
            String decisionId = "decision_" + qcr.getId();

            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("outcome",     qcr.getFinalDecision().name());
            meta.put("reviewer",    qcr.getReviewedBy() != null ? qcr.getReviewedBy().getUsername() : null);
            meta.put("reviewedAt",  ts(qcr.getReviewedAt()));
            meta.put("notes",       qcr.getReviewerNotes());
            meta.put("passedRules", qcr.getPassedCount());
            meta.put("failedRules", qcr.getFailedCount());
            meta.put("verifyCount", qcr.getVerifyCount());

            nodes.add(node(decisionId, "Decision: " + qcr.getFinalDecision().name(),
                "DECISION", qcr.getFinalDecision().name(), meta));

            String decisionSrc = lastSessionId != null ? lastSessionId : fileNodeId;
            links.add(link(decisionSrc, decisionId, "RESULTED_IN", ts(qcr.getReviewedAt())));

            // SUBMIT node
            String submitId = "submit_" + qcr.getId();
            Map<String, Object> submitMeta = new LinkedHashMap<>();
            submitMeta.put("submittedAt",    ts(qcr.getReviewedAt()));
            submitMeta.put("submittedBy",    qcr.getReviewedBy() != null ? qcr.getReviewedBy().getUsername() : null);
            submitMeta.put("finalDecision",  qcr.getFinalDecision().name());

            nodes.add(node(submitId, "Submitted", "SUBMIT", "DONE", submitMeta));
            links.add(link(decisionId, submitId, "LED_TO", ts(qcr.getReviewedAt())));

            log.info("[graph/file] fileId={} → decision={} submit added", fileId, qcr.getFinalDecision());
        }

        log.info("[graph/file] fileId={} returning {} nodes, {} links", fileId, nodes.size(), links.size());
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
                if (seen.add(fileNodeId)) nodes.add(fileNode(file, qcByFileId.get(file.getId()), batch));
                links.add(link(batchNodeId, fileNodeId, "CONTAINS", null));
            }
        }

        log.info("[graph/reviewer] userId={} → {} nodes, {} links", userId, nodes.size(), links.size());
        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Search / filter ───────────────────────────────────────────────────────

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
                try {
                    if (batch.getStatus() != BatchStatus.valueOf(status.toUpperCase())) continue;
                } catch (IllegalArgumentException ignored) { continue; }
            }
            if (qLow != null) {
                boolean hit =
                    (batch.getParentBatchId() != null && batch.getParentBatchId().toLowerCase().contains(qLow)) ||
                    (batch.getClient() != null && batch.getClient().getName() != null && batch.getClient().getName().toLowerCase().contains(qLow)) ||
                    (batch.getAssignedReviewer() != null && batch.getAssignedReviewer().getUsername() != null && batch.getAssignedReviewer().getUsername().toLowerCase().contains(qLow));
                if (!hit) continue;
            }

            String batchNodeId = "batch_" + batch.getId();
            if (seen.add(batchNodeId)) nodes.add(batchNode(batch));

            List<BatchFile> files = batchFileRepository.findByBatchId(batch.getId());
            List<QCResult>  qcrs  = qcResultRepository.findByBatchId(batch.getId());
            Map<Long, QCResult> qcByFileId = buildQcByFileId(qcrs);

            for (BatchFile file : files) {
                String fileNodeId = "file_" + file.getId();
                if (seen.add(fileNodeId)) nodes.add(fileNode(file, qcByFileId.get(file.getId()), batch));
                links.add(link(batchNodeId, fileNodeId, "CONTAINS", null));
                if (nodes.size() >= 300) break;
            }
            if (nodes.size() >= 300) break;
        }

        log.info("[graph/search] q='{}' status='{}' → {} nodes, {} links", q, status, nodes.size(), links.size());
        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Node builders ─────────────────────────────────────────────────────────

    private Map<String, Object> batchNode(Batch b) {
        Client client   = b.getClient();
        User   reviewer = b.getAssignedReviewer();

        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("status",       b.getStatus() != null ? b.getStatus().name() : null);
        meta.put("client",       client   != null ? client.getName()           : null);
        meta.put("clientCode",   client   != null ? client.getCode()           : null);
        meta.put("reviewer",     reviewer != null ? reviewer.getUsername()     : null);
        meta.put("reviewerEmail",reviewer != null ? reviewer.getEmail()        : null);
        meta.put("fileCount",    b.getFileCount());
        meta.put("createdAt",    ts(b.getCreatedAt()));
        meta.put("updatedAt",    ts(b.getUpdatedAt()));

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
        meta.put("batchId",       batch  != null ? batch.getId()           : null);
        meta.put("batchName",     batch  != null ? batch.getParentBatchId(): null);
        meta.put("client",        client != null ? client.getName()        : null);
        meta.put("reviewer",      reviewer != null ? reviewer.getUsername(): null);
        meta.put("fileType",      file.getFileType() != null ? file.getFileType().name() : null);
        meta.put("orderId",       file.getOrderId());
        meta.put("uploadedAt",    ts(file.getCreatedAt()));
        meta.put("lastActionAt",  ts(file.getUpdatedAt()));
        meta.put("fileSize",      file.getFileSize());

        if (qcr != null) {
            meta.put("qcDecision",   qcr.getQcDecision()   != null ? qcr.getQcDecision().name()   : null);
            meta.put("finalDecision",qcr.getFinalDecision() != null ? qcr.getFinalDecision().name(): null);
            meta.put("qcReviewer",   qcr.getReviewedBy()   != null ? qcr.getReviewedBy().getUsername(): null);
            meta.put("passedRules",  qcr.getPassedCount());
            meta.put("failedRules",  qcr.getFailedCount());
            meta.put("verifyCount",  qcr.getVerifyCount());
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

    // ── Shared utilities ──────────────────────────────────────────────────────

    private static Map<Long, QCResult> buildQcByFileId(List<QCResult> qcrs) {
        Map<Long, QCResult> map = new HashMap<>();
        for (QCResult qcr : qcrs) {
            // getBatchFile() is safe inside @Transactional
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

    @FunctionalInterface
    private interface Getter<T, R> { R get(T t); }

    private static <T> String safeStr(T obj, Getter<T, String> getter) {
        return obj != null ? getter.get(obj) : "null";
    }
}
