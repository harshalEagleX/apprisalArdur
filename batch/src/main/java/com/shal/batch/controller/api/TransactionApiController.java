package com.shal.batch.controller.api;

import com.shal.batch.service.TransactionService;
import com.shal.common.entity.AppraisalTransaction;
import com.shal.common.entity.Client;
import com.shal.common.repository.AppraisalTransactionRepository;
import com.shal.common.security.UserPrincipal;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * REST API for the AppraisalTransaction layer.
 *
 * Transactions sit above batches: one AMC order that may span multiple SHAL
 * batch submissions (original + revisions). All endpoints require ADMIN role
 * (enforced by SecurityConfig's /api/admin/** rule).
 */
@RestController
@RequestMapping("/api/admin/transactions")
public class TransactionApiController {

    private final TransactionService transactionService;
    private final AppraisalTransactionRepository transactionRepository;

    public TransactionApiController(TransactionService transactionService,
                                    AppraisalTransactionRepository transactionRepository) {
        this.transactionService = transactionService;
        this.transactionRepository = transactionRepository;
    }

    /** Dashboard overview — status counts. */
    @GetMapping("/stats")
    public ResponseEntity<Map<String, Long>> stats() {
        return ResponseEntity.ok(transactionService.statusCounts());
    }

    /** List transactions, newest first, paginated. */
    @GetMapping
    public ResponseEntity<List<Map<String, Object>>> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        Page<AppraisalTransaction> pageResult = transactionRepository.findAll(
                PageRequest.of(page, size, Sort.by("createdAt").descending()));
        List<Map<String, Object>> body = pageResult.getContent().stream()
                .map(this::toView)
                .toList();
        return ResponseEntity.ok(body);
    }

    /** Get a single transaction. */
    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> get(@PathVariable Long id) {
        return transactionService.findById(id)
                .map(tx -> ResponseEntity.ok(toView(tx)))
                .orElse(ResponseEntity.notFound().build());
    }

    /**
     * Create a new transaction (called when intake team receives a new AMC order
     * or revision before uploading the ZIP).
     */
    @PostMapping
    public ResponseEntity<Map<String, Object>> create(
            @RequestBody Map<String, Object> req,
            @AuthenticationPrincipal UserPrincipal principal) {
        String amcCode = stringField(req, "amc_code");
        String orderNumber = stringField(req, "order_number");
        String address = stringField(req, "property_address");
        String revisedFromRef = stringField(req, "revised_from_ref");
        String slaDue = stringField(req, "sla_due_at");

        Client client = principal != null && principal.getUser().getClient() != null
                ? principal.getUser().getClient() : null;

        LocalDateTime slaDueAt = null;
        if (slaDue != null && !slaDue.isBlank()) {
            try { slaDueAt = LocalDateTime.parse(slaDue); } catch (Exception ignored) { }
        }

        AppraisalTransaction tx = transactionService.createTransaction(
                amcCode, orderNumber, address, client, revisedFromRef, slaDueAt);
        return ResponseEntity.ok(toView(tx));
    }

    /** Link a batch to a transaction. */
    @PostMapping("/{id}/link-batch/{batchId}")
    public ResponseEntity<Map<String, Object>> linkBatch(
            @PathVariable Long id,
            @PathVariable Long batchId) {
        transactionService.linkBatchToTransaction(batchId, id);
        return ResponseEntity.ok(Map.of("success", true, "transactionId", id, "batchId", batchId));
    }

    /** Mark a rejection as sent to the AMC — transaction moves to AWAITING_REVISION. */
    @PostMapping("/{id}/rejection-sent")
    public ResponseEntity<Map<String, Object>> rejectionSent(@PathVariable Long id) {
        transactionService.onRejectionSent(id);
        return transactionService.findById(id)
                .map(tx -> ResponseEntity.ok(toView(tx)))
                .orElse(ResponseEntity.notFound().build());
    }

    /** Manually abandon a transaction. */
    @PostMapping("/{id}/abandon")
    public ResponseEntity<Map<String, Object>> abandon(@PathVariable Long id) {
        transactionService.abandonTransaction(id);
        return ResponseEntity.ok(Map.of("success", true, "transactionId", id));
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private Map<String, Object> toView(AppraisalTransaction tx) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", tx.getId());
        m.put("transactionRef", tx.getTransactionRef());
        m.put("amcCode", tx.getAmcCode());
        m.put("orderNumber", tx.getOrderNumber());
        m.put("propertyAddress", tx.getPropertyAddress());
        m.put("status", tx.getStatus() != null ? tx.getStatus().name() : null);
        m.put("revisionNumber", tx.getRevisionNumber());
        m.put("revisedFromRef", tx.getRevisedFrom() != null ? tx.getRevisedFrom().getTransactionRef() : null);
        m.put("receivedAt", ts(tx.getReceivedAt()));
        m.put("submittedAt", ts(tx.getSubmittedAt()));
        m.put("revisionSentAt", ts(tx.getRevisionSentAt()));
        m.put("closedAt", ts(tx.getClosedAt()));
        m.put("slaDueAt", ts(tx.getSlaDueAt()));
        m.put("createdAt", ts(tx.getCreatedAt()));
        return m;
    }

    private String ts(LocalDateTime dt) {
        return dt != null ? dt.toString() : null;
    }

    private String stringField(Map<String, Object> req, String key) {
        Object v = req.get(key);
        return v != null && !v.toString().isBlank() ? v.toString().trim() : null;
    }
}
