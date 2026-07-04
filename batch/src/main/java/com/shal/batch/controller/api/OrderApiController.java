package com.shal.batch.controller.api;

import com.shal.common.entity.AppraisalTransaction;
import com.shal.common.entity.Batch;
import com.shal.common.entity.BatchFile;
import com.shal.common.entity.Client;
import com.shal.common.entity.OrderDocumentStatus;
import com.shal.common.entity.QCResult;
import com.shal.common.entity.User;
import com.shal.common.repository.AppraisalTransactionRepository;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.repository.BatchRepository;
import com.shal.common.repository.QCResultRepository;
import com.shal.common.security.UserPrincipal;
import com.shal.common.service.OrderResolutionService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.lang.NonNull;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * REST API for Order (AppraisalTransaction) operations — ADMIN only.
 *
 * "Order" is the canonical business entity per the order-centric design: one
 * real-world AMC order, with its documents, QC result, and lifecycle status
 * all reachable here regardless of which batch(es) it was uploaded through.
 * The Java entity backing this is {@link AppraisalTransaction} — kept as-is
 * to avoid a disruptive table rename, exposed to the API/frontend as "Order".
 */
@RestController
@RequestMapping("/api/admin/orders")
@PreAuthorize("hasRole('ADMIN')")
public class OrderApiController {

    private static final Logger log = LoggerFactory.getLogger(OrderApiController.class);

    private final AppraisalTransactionRepository orderRepository;
    private final BatchFileRepository batchFileRepository;
    private final BatchRepository batchRepository;
    private final QCResultRepository qcResultRepository;
    private final OrderResolutionService orderResolutionService;
    private final com.shal.common.repository.UserRepository userRepository;
    private final com.shal.common.service.BusinessEventService businessEventService;

    public OrderApiController(AppraisalTransactionRepository orderRepository,
                              BatchFileRepository batchFileRepository,
                              BatchRepository batchRepository,
                              QCResultRepository qcResultRepository,
                              OrderResolutionService orderResolutionService,
                              com.shal.common.repository.UserRepository userRepository,
                              com.shal.common.service.BusinessEventService businessEventService) {
        this.orderRepository = orderRepository;
        this.batchFileRepository = batchFileRepository;
        this.batchRepository = batchRepository;
        this.qcResultRepository = qcResultRepository;
        this.orderResolutionService = orderResolutionService;
        this.userRepository = userRepository;
        this.businessEventService = businessEventService;
    }

    @GetMapping
    public ResponseEntity<?> getOrders(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String documentStatus,
            @RequestParam(required = false) String search,
            @AuthenticationPrincipal UserPrincipal principal) {
        OrderDocumentStatus status = null;
        if (documentStatus != null && !documentStatus.isBlank()) {
            try {
                status = OrderDocumentStatus.valueOf(documentStatus.toUpperCase());
            } catch (IllegalArgumentException e) {
                return ResponseEntity.badRequest().body(Map.of("error", "Unknown documentStatus: " + documentStatus));
            }
        }

        // Client-scoped admins only see their own orders; a super-admin (no client) sees all.
        Client adminClient = principal.getUser().getClient();
        Long clientId = adminClient != null ? adminClient.getId() : null;

        Page<AppraisalTransaction> orderPage = orderRepository.search(
                clientId, status, (search != null && !search.isBlank()) ? search : null,
                PageRequest.of(page, size, Sort.by("updatedAt").descending()));

        return ResponseEntity.ok(Map.of(
                "content", orderPage.getContent().stream().map(this::toSummary).toList(),
                "totalPages", orderPage.getTotalPages(),
                "number", orderPage.getNumber(),
                "totalElements", orderPage.getTotalElements()));
    }

    @GetMapping("/statuses")
    public ResponseEntity<List<String>> getStatuses() {
        return ResponseEntity.ok(java.util.Arrays.stream(OrderDocumentStatus.values()).map(Enum::name).toList());
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getOrder(@PathVariable @NonNull Long id,
                                      @AuthenticationPrincipal UserPrincipal principal) {
        Optional<AppraisalTransaction> orderOpt = orderRepository.findWithClientById(id);
        if (orderOpt.isEmpty()) return ResponseEntity.notFound().build();
        AppraisalTransaction order = orderOpt.get();

        Client adminClient = principal.getUser().getClient();
        if (adminClient != null && (order.getClient() == null || !adminClient.getId().equals(order.getClient().getId()))) {
            return ResponseEntity.status(403).body(Map.of("error", "ACCESS_DENIED",
                    "message", "You do not have access to this order."));
        }

        return ResponseEntity.ok(toDetail(order));
    }

    /**
     * One-time, idempotent reconciliation for files ingested before Order
     * resolution existed — links them to a canonical Order using the same
     * content-hash → orderId → propertySetName identity matching used at
     * intake. Safe to re-run.
     */
    @PostMapping("/backfill")
    public ResponseEntity<?> backfill(@AuthenticationPrincipal UserPrincipal principal) {
        User actor = principal.getUser();
        log.info("Order backfill triggered by {}", actor.getUsername());
        OrderResolutionService.BackfillSummary summary = orderResolutionService.backfillUnresolvedFiles(actor);
        return ResponseEntity.ok(Map.of(
                "filesProcessed", summary.filesProcessed(),
                "ordersTouched", summary.ordersTouched(),
                "ordersCreated", summary.ordersCreated(),
                "duplicatesFound", summary.duplicatesFound()));
    }

    /**
     * Allocate a single Order to a reviewer (or clear the allocation when reviewerId is
     * null/absent). Assignment is per-Order by design: a batch may hold dozens of orders,
     * so each is routed to a reviewer independently instead of dumping a whole batch on
     * one person.
     */
    @PostMapping("/{id}/assign")
    public ResponseEntity<?> assignReviewer(@PathVariable @NonNull Long id,
                                            @RequestBody(required = false) Map<String, Object> body,
                                            @AuthenticationPrincipal UserPrincipal principal) {
        Optional<AppraisalTransaction> orderOpt = orderRepository.findWithClientById(id);
        if (orderOpt.isEmpty()) return ResponseEntity.notFound().build();
        AppraisalTransaction order = orderOpt.get();

        Optional<ResponseEntity<?>> denied = assertOrderAccess(principal, order);
        if (denied.isPresent()) return denied.get();

        Long reviewerId = parseLong(body != null ? body.get("reviewerId") : null);
        ResponseEntity<?> result = applyAssignment(order, reviewerId, principal.getUser());
        if (result != null) return result;
        return ResponseEntity.ok(toDetail(order));
    }

    /**
     * Bulk-allocate several selected Orders to one reviewer in a single action (or clear
     * them when reviewerId is null). Powers "select N orders → assign" from the Order view.
     */
    @PostMapping("/assign")
    public ResponseEntity<?> assignReviewerBulk(@RequestBody Map<String, Object> body,
                                                @AuthenticationPrincipal UserPrincipal principal) {
        java.util.LinkedHashSet<Long> orderIds = new java.util.LinkedHashSet<>();
        Object raw = body != null ? body.get("orderIds") : null;
        if (raw instanceof List<?> list) {
            for (Object o : list) {
                Long v = parseLong(o);
                if (v != null) orderIds.add(v);
            }
        }
        if (orderIds.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "orderIds is required (non-empty list)."));
        }
        Long reviewerId = parseLong(body.get("reviewerId"));

        List<Long> assigned = new ArrayList<>();
        List<Long> skipped = new ArrayList<>();
        for (Long orderId : orderIds) {
            Optional<AppraisalTransaction> orderOpt = orderRepository.findWithClientById(orderId);
            if (orderOpt.isEmpty()) { skipped.add(orderId); continue; }
            AppraisalTransaction order = orderOpt.get();
            if (assertOrderAccess(principal, order).isPresent()) { skipped.add(orderId); continue; }
            ResponseEntity<?> err = applyAssignment(order, reviewerId, principal.getUser());
            if (err != null) { skipped.add(orderId); continue; }
            assigned.add(orderId);
        }
        return ResponseEntity.ok(Map.of(
                "assignedCount", assigned.size(),
                "assignedOrderIds", assigned,
                "skippedOrderIds", skipped,
                "reviewerId", reviewerId != null ? reviewerId : ""));
    }

    /**
     * Sets (or clears when reviewerId is null) the Order's reviewer after validating the
     * target user is a REVIEWER. Returns a non-null error ResponseEntity on failure, or
     * null on success (the order is mutated + saved).
     */
    private ResponseEntity<?> applyAssignment(AppraisalTransaction order, Long reviewerId, User actor) {
        User reviewer = null;
        if (reviewerId != null) {
            Optional<User> reviewerOpt = userRepository.findById(reviewerId);
            if (reviewerOpt.isEmpty()) {
                return ResponseEntity.badRequest().body(Map.of("error", "Reviewer not found: " + reviewerId));
            }
            reviewer = reviewerOpt.get();
            if (reviewer.getRole() != com.shal.common.entity.Role.REVIEWER) {
                return ResponseEntity.badRequest().body(Map.of(
                        "error", "User " + reviewer.getUsername() + " is not a REVIEWER."));
            }
        }
        order.setAssignedReviewer(reviewer);
        order.setReviewerAssignedAt(reviewer != null ? com.shal.common.util.AppTime.now() : null);
        orderRepository.save(order);

        businessEventService.record(
                reviewer != null ? "ORDER_REVIEWER_ASSIGNED" : "ORDER_REVIEWER_UNASSIGNED",
                actor, "java", reviewer != null ? "ASSIGNED" : "UNASSIGNED",
                "AppraisalTransaction", order.getId(), null, null, null, null,
                Map.of("orderRef", String.valueOf(order.getTransactionRef()),
                       "reviewerId", reviewerId != null ? reviewerId : ""));
        log.info("Order {} reviewer {} by {}", order.getTransactionRef(),
                reviewer != null ? "→ " + reviewer.getUsername() : "cleared", actor.getUsername());
        return null;
    }

    /**
     * Auto-assign: balance unassigned Orders across active reviewers (least-loaded first).
     * This runs ONLY when the admin explicitly triggers it — assignment is never automatic
     * at upload time, so an admin who prefers to allocate manually is never overridden.
     * Optional body {orderIds:[...]} limits the pool to those orders (still only the
     * unassigned ones); otherwise every unassigned order in scope is distributed.
     */
    @PostMapping("/auto-assign")
    public ResponseEntity<?> autoAssign(@RequestBody(required = false) Map<String, Object> body,
                                        @AuthenticationPrincipal UserPrincipal principal) {
        Client adminClient = principal.getUser().getClient();
        Long clientId = adminClient != null ? adminClient.getId() : null;

        // Active reviewers only. A client-scoped admin distributes to their own client's
        // reviewers; a super-admin (no client) may use any reviewer.
        List<User> reviewers = userRepository.findByRole(com.shal.common.entity.Role.REVIEWER).stream()
                .filter(u -> Boolean.TRUE.equals(u.getActive()) || u.getActive() == null)
                .filter(u -> clientId == null
                        || (u.getClient() != null && clientId.equals(u.getClient().getId())))
                .toList();
        if (reviewers.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "No active reviewers are available to auto-assign to."));
        }

        // Candidate pool: unassigned orders in scope, optionally narrowed to a selection.
        List<AppraisalTransaction> pool = orderRepository.findUnassigned(clientId);
        Object raw = body != null ? body.get("orderIds") : null;
        if (raw instanceof List<?> list && !list.isEmpty()) {
            java.util.Set<Long> wanted = new java.util.HashSet<>();
            for (Object o : list) { Long v = parseLong(o); if (v != null) wanted.add(v); }
            pool = pool.stream().filter(o -> wanted.contains(o.getId())).toList();
        }
        if (pool.isEmpty()) {
            return ResponseEntity.ok(Map.of(
                    "message", "No unassigned orders to distribute.",
                    "assignedCount", 0));
        }

        // Seed each reviewer's live load so distribution stays balanced across repeated runs.
        Map<Long, Long> load = new HashMap<>();
        Map<Long, User> reviewerById = new HashMap<>();
        for (User r : reviewers) {
            load.put(r.getId(), orderRepository.countByAssignedReviewer_Id(r.getId()));
            reviewerById.put(r.getId(), r);
        }

        int assigned = 0;
        Map<Long, Integer> perReviewer = new LinkedHashMap<>();
        for (AppraisalTransaction order : pool) {
            Long targetId = load.entrySet().stream()
                    .min(Map.Entry.comparingByValue())
                    .map(Map.Entry::getKey)
                    .orElse(reviewers.get(0).getId());
            order.setAssignedReviewer(reviewerById.get(targetId));
            order.setReviewerAssignedAt(com.shal.common.util.AppTime.now());
            orderRepository.save(order);
            load.merge(targetId, 1L, Long::sum);
            perReviewer.merge(targetId, 1, Integer::sum);
            assigned++;
        }

        businessEventService.record("ORDER_REVIEWER_AUTO_ASSIGNED", principal.getUser(), "java", "ASSIGNED",
                "AppraisalTransaction", null, null, null, null, null,
                Map.of("assignedCount", assigned, "reviewerCount", reviewers.size()));
        log.info("Auto-assigned {} order(s) across {} reviewer(s) by {}",
                assigned, reviewers.size(), principal.getUser().getUsername());

        return ResponseEntity.ok(Map.of(
                "message", "Auto-assigned " + assigned + " order(s) across " + reviewers.size() + " reviewer(s).",
                "assignedCount", assigned,
                "distribution", perReviewer));
    }

    /** Client-scoped admins may only act on their own client's orders. */
    private Optional<ResponseEntity<?>> assertOrderAccess(UserPrincipal principal, AppraisalTransaction order) {
        Client adminClient = principal.getUser().getClient();
        if (adminClient != null && (order.getClient() == null
                || !adminClient.getId().equals(order.getClient().getId()))) {
            return Optional.of(ResponseEntity.status(403).body(Map.of("error", "ACCESS_DENIED",
                    "message", "You do not have access to this order.")));
        }
        return Optional.empty();
    }

    private static Long parseLong(Object o) {
        if (o == null) return null;
        String s = String.valueOf(o).trim();
        if (s.isEmpty() || "null".equalsIgnoreCase(s)) return null;
        try { return Long.valueOf(s); } catch (NumberFormatException e) { return null; }
    }

    // ── DTO mapping ──────────────────────────────────────────────────────────

    private Map<String, Object> toSummary(AppraisalTransaction order) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", order.getId());
        m.put("transactionRef", order.getTransactionRef());
        m.put("status", order.getStatus() != null ? order.getStatus().name() : null);
        m.put("documentStatus", order.getDocumentStatus() != null ? order.getDocumentStatus().name() : null);
        m.put("propertyAddress", order.getPropertyAddress());
        m.put("amcCode", order.getAmcCode());
        m.put("orderNumber", order.getOrderNumber());
        m.put("revisionNumber", order.getRevisionNumber());
        m.put("createdAt", order.getCreatedAt() != null ? order.getCreatedAt().toString() : null);
        m.put("updatedAt", order.getUpdatedAt() != null ? order.getUpdatedAt().toString() : null);
        if (order.getClient() != null) {
            m.put("client", Map.of(
                    "id", order.getClient().getId(),
                    "name", order.getClient().getName() != null ? order.getClient().getName() : "",
                    "code", order.getClient().getCode() != null ? order.getClient().getCode() : ""));
        } else {
            m.put("client", null);
        }
        long docCount = batchFileRepository.findActiveByOrderId(order.getId()).size();
        m.put("activeDocumentCount", docCount);
        if (order.getAssignedReviewer() != null) {
            User r = order.getAssignedReviewer();
            m.put("assignedReviewer", Map.of(
                    "id", r.getId(),
                    "username", r.getUsername() != null ? r.getUsername() : "",
                    "fullName", r.getFullName() != null ? r.getFullName() : ""));
        } else {
            m.put("assignedReviewer", null);
        }
        m.put("reviewerAssignedAt", order.getReviewerAssignedAt() != null
                ? order.getReviewerAssignedAt().toString() : null);
        return m;
    }

    private Map<String, Object> toDetail(AppraisalTransaction order) {
        Map<String, Object> m = toSummary(order);

        // Full document history (active + superseded) for this order, most recent first.
        List<BatchFile> allDocs = batchFileRepository.findAllByOrderId(order.getId());
        List<Map<String, Object>> docDtos = allDocs.stream().map(f -> {
            Map<String, Object> fm = new HashMap<>();
            fm.put("id", f.getId());
            fm.put("filename", f.getFilename());
            fm.put("fileType", f.getFileType() != null ? f.getFileType().name() : null);
            fm.put("status", f.getStatus() != null ? f.getStatus().name() : null);
            fm.put("contentVersion", f.getContentVersion());
            fm.put("active", f.isActive());
            fm.put("supersededAt", f.getSupersededAt() != null ? f.getSupersededAt().toString() : null);
            fm.put("batchId", f.getBatch() != null ? f.getBatch().getId() : null);
            fm.put("createdAt", f.getCreatedAt() != null ? f.getCreatedAt().toString() : null);
            return fm;
        }).toList();
        m.put("documents", docDtos);

        // Active QCResult for the order's active appraisal document, if any.
        allDocs.stream()
                .filter(BatchFile::isActive)
                .filter(f -> f.getFileType() == com.shal.common.entity.FileType.APPRAISAL)
                .findFirst()
                .flatMap(appraisal -> qcResultRepository.findActiveByBatchFileId(appraisal.getId()))
                .ifPresent(qc -> m.put("activeQcResult", toQcSummary(qc)));

        // Batch-membership rollup: every batch (upload event) that touched this order.
        List<Long> batchIds = batchFileRepository.findDistinctBatchIdsByOrderId(order.getId());
        List<Batch> batches = batchRepository.findAllById(batchIds);
        List<Map<String, Object>> batchHistory = new ArrayList<>();
        for (Batch b : batches) {
            Map<String, Object> bm = new HashMap<>();
            bm.put("id", b.getId());
            bm.put("parentBatchId", b.getParentBatchId());
            bm.put("status", b.getStatus() != null ? b.getStatus().name() : null);
            bm.put("createdAt", b.getCreatedAt() != null ? b.getCreatedAt().toString() : null);
            batchHistory.add(bm);
        }
        batchHistory.sort((a, b) -> String.valueOf(b.get("createdAt")).compareTo(String.valueOf(a.get("createdAt"))));
        m.put("batchHistory", batchHistory);

        return m;
    }

    private Map<String, Object> toQcSummary(QCResult qc) {
        Map<String, Object> qm = new HashMap<>();
        qm.put("id", qc.getId());
        qm.put("qcDecision", qc.getQcDecision() != null ? qc.getQcDecision().name() : null);
        qm.put("finalDecision", qc.getFinalDecision() != null ? qc.getFinalDecision().name() : null);
        qm.put("totalRules", qc.getTotalRules());
        qm.put("passedCount", qc.getPassedCount());
        qm.put("failedCount", qc.getFailedCount());
        qm.put("verifyCount", qc.getVerifyCount());
        qm.put("processedAt", qc.getCreatedAt() != null ? qc.getCreatedAt().toString() : null);
        return qm;
    }
}
