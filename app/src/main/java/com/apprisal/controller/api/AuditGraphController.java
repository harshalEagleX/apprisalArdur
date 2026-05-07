package com.apprisal.controller.api;

import com.apprisal.common.entity.*;
import com.apprisal.common.repository.*;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Graph API for the Audit Intelligence Graph view.
 * Each endpoint returns { nodes: [...], links: [...] } shaped for force-graph.
 */
@RestController
@RequestMapping("/api/graph")
@PreAuthorize("hasRole('ADMIN')")
public class AuditGraphController {

    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final QCResultRepository qcResultRepository;
    private final AuditLogRepository auditLogRepository;
    private final UserRepository userRepository;

    public AuditGraphController(
            BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            QCResultRepository qcResultRepository,
            AuditLogRepository auditLogRepository,
            UserRepository userRepository) {
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.qcResultRepository = qcResultRepository;
        this.auditLogRepository = auditLogRepository;
        this.userRepository = userRepository;
    }

    // ── Overview: all batch nodes, no deep traversal ─────────────────────────

    @GetMapping("/overview")
    public ResponseEntity<Map<String, Object>> overview(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "200") int size) {

        var batches = batchRepository.findAll(
            PageRequest.of(page, Math.min(size, 300), Sort.by("createdAt").descending())
        ).getContent();

        List<Map<String, Object>> nodes = new ArrayList<>();
        for (Batch b : batches) {
            nodes.add(batchNode(b));
        }
        return ResponseEntity.ok(graph(nodes, List.of()));
    }

    // ── Batch subgraph: batch + all file nodes ────────────────────────────────

    @GetMapping("/batch/{batchId}")
    public ResponseEntity<Map<String, Object>> batchSubgraph(@PathVariable Long batchId) {
        var batchOpt = batchRepository.findWithFilesById(batchId);
        if (batchOpt.isEmpty()) return ResponseEntity.notFound().build();

        Batch batch = batchOpt.get();
        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        nodes.add(batchNode(batch));
        String batchNodeId = "batch_" + batch.getId();

        // One query to get all QCResults for this batch
        List<QCResult> qcrs = qcResultRepository.findByBatchId(batchId);
        Map<Long, QCResult> qcByFileId = qcrs.stream()
            .filter(qr -> qr.getBatchFile() != null)
            .collect(Collectors.toMap(
                qr -> qr.getBatchFile().getId(),
                qr -> qr,
                (a, b) -> a
            ));

        for (BatchFile file : batch.getFiles()) {
            nodes.add(fileNode(file, qcByFileId.get(file.getId()), batch));
            links.add(link(batchNodeId, "file_" + file.getId(), "CONTAINS", null));
        }

        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── File subgraph: complete audit journey for one file ────────────────────

    @GetMapping("/file/{fileId}")
    public ResponseEntity<Map<String, Object>> fileSubgraph(@PathVariable Long fileId) {
        var fileOpt = batchFileRepository.findWithBatchAndReviewerById(fileId);
        if (fileOpt.isEmpty()) return ResponseEntity.notFound().build();

        BatchFile file = fileOpt.get();
        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        var qcOpt = qcResultRepository.findByBatchFileId(fileId);
        QCResult qcr = qcOpt.orElse(null);

        String fileNodeId = "file_" + fileId;
        nodes.add(fileNode(file, qcr, file.getBatch()));

        if (qcr == null) {
            return ResponseEntity.ok(graph(nodes, links));
        }

        // Fetch audit logs for this QCResult (REVIEW_SESSION_STARTED events)
        List<AuditLog> sessionLogs = auditLogRepository.findByEntityTypeAndEntityId("QCResult", qcr.getId());
        sessionLogs.sort(Comparator.comparing(
            al -> al.getCreatedAt() != null ? al.getCreatedAt() : LocalDateTime.MIN
        ));

        String prevNodeId = fileNodeId;
        String lastSessionId = null;
        int sessionIndex = 0;

        for (AuditLog log : sessionLogs) {
            if (!"REVIEW_SESSION_STARTED".equals(log.getAction())) continue;

            sessionIndex++;
            String sessionNodeId = "session_" + log.getId();
            lastSessionId = sessionNodeId;

            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("reviewer", log.getUser() != null ? log.getUser().getUsername() : "system");
            meta.put("startedAt", ts(log.getCreatedAt()));
            meta.put("sessionIndex", sessionIndex);
            meta.put("qcResultId", qcr.getId());

            nodes.add(node(sessionNodeId, "Session #" + sessionIndex, "REVIEW_SESSION", "ACTIVE", meta));

            String edgeType = sessionIndex == 1 ? "HAS_SESSION" : "RE_REVIEW";
            links.add(link(prevNodeId, sessionNodeId, edgeType, ts(log.getCreatedAt())));
            prevNodeId = sessionNodeId;
        }

        // DECISION node from QCResult.finalDecision
        if (qcr.getFinalDecision() != null) {
            String decisionId = "decision_" + qcr.getId();

            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("outcome", qcr.getFinalDecision().name());
            meta.put("reviewer", qcr.getReviewedBy() != null ? qcr.getReviewedBy().getUsername() : null);
            meta.put("reviewedAt", ts(qcr.getReviewedAt()));
            meta.put("notes", qcr.getReviewerNotes());
            meta.put("passedRules", qcr.getPassedCount());
            meta.put("failedRules", qcr.getFailedCount());
            meta.put("verifyCount", qcr.getVerifyCount());

            nodes.add(node(decisionId, "Decision: " + qcr.getFinalDecision().name(), "DECISION",
                qcr.getFinalDecision().name(), meta));

            String decisionSource = lastSessionId != null ? lastSessionId : fileNodeId;
            links.add(link(decisionSource, decisionId, "RESULTED_IN", ts(qcr.getReviewedAt())));

            // SUBMIT node
            String submitId = "submit_" + qcr.getId();
            Map<String, Object> submitMeta = new LinkedHashMap<>();
            submitMeta.put("submittedAt", ts(qcr.getReviewedAt()));
            submitMeta.put("submittedBy", qcr.getReviewedBy() != null ? qcr.getReviewedBy().getUsername() : null);
            submitMeta.put("finalDecision", qcr.getFinalDecision().name());

            nodes.add(node(submitId, "Submitted", "SUBMIT", "DONE", submitMeta));
            links.add(link(decisionId, submitId, "LED_TO", ts(qcr.getReviewedAt())));
        }

        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Reviewer subgraph: batches + files this reviewer touched ─────────────

    @GetMapping("/reviewer/{userId}")
    public ResponseEntity<Map<String, Object>> reviewerGraph(@PathVariable Long userId) {
        List<Batch> batches = batchRepository.findByAssignedReviewerId(userId);
        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();
        Set<String> seen = new HashSet<>();

        for (Batch batch : batches) {
            String batchNodeId = "batch_" + batch.getId();
            if (seen.add(batchNodeId)) nodes.add(batchNode(batch));

            List<BatchFile> files = batchFileRepository.findByBatchId(batch.getId());
            List<QCResult> qcrs = qcResultRepository.findByBatchId(batch.getId());
            Map<Long, QCResult> qcByFileId = qcrs.stream()
                .filter(qr -> qr.getBatchFile() != null)
                .collect(Collectors.toMap(qr -> qr.getBatchFile().getId(), qr -> qr, (a, b) -> a));

            for (BatchFile file : files) {
                String fileNodeId = "file_" + file.getId();
                if (seen.add(fileNodeId)) nodes.add(fileNode(file, qcByFileId.get(file.getId()), batch));
                links.add(link(batchNodeId, fileNodeId, "CONTAINS", null));
            }
        }

        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Search / filter ───────────────────────────────────────────────────────

    @GetMapping("/search")
    public ResponseEntity<Map<String, Object>> search(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) Long reviewer,
            @RequestParam(required = false) Long client) {

        var allBatches = batchRepository.findAll(
            PageRequest.of(0, 300, Sort.by("createdAt").descending())
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
            List<QCResult> qcrs = qcResultRepository.findByBatchId(batch.getId());
            Map<Long, QCResult> qcByFileId = qcrs.stream()
                .filter(qr -> qr.getBatchFile() != null)
                .collect(Collectors.toMap(qr -> qr.getBatchFile().getId(), qr -> qr, (a, b) -> a));

            for (BatchFile file : files) {
                String fileNodeId = "file_" + file.getId();
                if (seen.add(fileNodeId)) nodes.add(fileNode(file, qcByFileId.get(file.getId()), batch));
                links.add(link(batchNodeId, fileNodeId, "CONTAINS", null));
            }
        }

        return ResponseEntity.ok(graph(nodes, links));
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private Map<String, Object> batchNode(Batch b) {
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("status", b.getStatus() != null ? b.getStatus().name() : null);
        meta.put("client", b.getClient() != null ? b.getClient().getName() : null);
        meta.put("clientCode", b.getClient() != null ? b.getClient().getCode() : null);
        meta.put("reviewer", b.getAssignedReviewer() != null ? b.getAssignedReviewer().getUsername() : null);
        meta.put("fileCount", b.getFileCount());
        meta.put("createdAt", ts(b.getCreatedAt()));
        meta.put("updatedAt", ts(b.getUpdatedAt()));

        return node(
            "batch_" + b.getId(),
            b.getParentBatchId() != null ? b.getParentBatchId() : "Batch #" + b.getId(),
            "BATCH",
            b.getStatus() != null ? b.getStatus().name() : "UNKNOWN",
            meta
        );
    }

    private Map<String, Object> fileNode(BatchFile file, QCResult qcr, Batch batch) {
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("batchId", batch != null ? batch.getId() : null);
        meta.put("batchName", batch != null ? batch.getParentBatchId() : null);
        meta.put("client", batch != null && batch.getClient() != null ? batch.getClient().getName() : null);
        meta.put("fileType", file.getFileType() != null ? file.getFileType().name() : null);
        meta.put("orderId", file.getOrderId());
        meta.put("uploadedAt", ts(file.getCreatedAt()));
        meta.put("lastActionAt", ts(file.getUpdatedAt()));
        meta.put("fileSize", file.getFileSize());
        if (qcr != null) {
            meta.put("qcDecision", qcr.getQcDecision() != null ? qcr.getQcDecision().name() : null);
            meta.put("finalDecision", qcr.getFinalDecision() != null ? qcr.getFinalDecision().name() : null);
            meta.put("reviewer", qcr.getReviewedBy() != null ? qcr.getReviewedBy().getUsername() : null);
            meta.put("passedRules", qcr.getPassedCount());
            meta.put("failedRules", qcr.getFailedCount());
            meta.put("verifyCount", qcr.getVerifyCount());
            meta.put("reviewedAt", ts(qcr.getReviewedAt()));
        }

        return node(
            "file_" + file.getId(),
            file.getFilename() != null ? file.getFilename() : "File #" + file.getId(),
            "FILE",
            file.getStatus() != null ? file.getStatus().name() : "UNKNOWN",
            meta
        );
    }

    private static Map<String, Object> node(String id, String label, String type, String status, Map<String, Object> meta) {
        Map<String, Object> n = new LinkedHashMap<>();
        n.put("id", id);
        n.put("label", label);
        n.put("type", type);
        n.put("status", status);
        n.put("meta", meta != null ? meta : Map.of());
        return n;
    }

    private static Map<String, Object> link(String source, String target, String type, String timestamp) {
        Map<String, Object> l = new LinkedHashMap<>();
        l.put("source", source);
        l.put("target", target);
        l.put("type", type);
        if (timestamp != null) l.put("timestamp", timestamp);
        return l;
    }

    private static Map<String, Object> graph(List<Map<String, Object>> nodes, List<Map<String, Object>> links) {
        Map<String, Object> g = new LinkedHashMap<>();
        g.put("nodes", nodes);
        g.put("links", links);
        return g;
    }

    private static String ts(LocalDateTime dt) {
        return dt != null ? dt.toString() : null;
    }
}
