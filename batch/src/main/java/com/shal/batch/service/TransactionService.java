package com.shal.batch.service;

import com.shal.common.entity.*;
import com.shal.common.repository.AppraisalTransactionRepository;
import com.shal.common.repository.BatchRepository;
import com.shal.common.util.AppTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Business logic for AppraisalTransaction lifecycle.
 *
 * A transaction (one AMC order) sits above the Batch layer and survives across
 * multiple submission rounds. The service is responsible for:
 *  - Creating transactions at intake (from manifest or explicit API call)
 *  - Linking batches to transactions on upload
 *  - Advancing transaction status as batch outcomes are known
 *  - Recording the three timestamps that drive AMC turnaround metrics
 */
@Service
public class TransactionService {

    private static final Logger log = LoggerFactory.getLogger(TransactionService.class);

    /** Default turnaround SLA (hours) applied when the manifest omits sla_due_at. */
    @Value("${shal.sla.default-hours:48}")
    private long defaultSlaHours;

    private final AppraisalTransactionRepository transactionRepository;
    private final BatchRepository batchRepository;

    public TransactionService(AppraisalTransactionRepository transactionRepository,
                              BatchRepository batchRepository) {
        this.transactionRepository = transactionRepository;
        this.batchRepository = batchRepository;
    }

    @Transactional(readOnly = true)
    public Optional<AppraisalTransaction> findById(Long id) {
        return transactionRepository.findById(id);
    }

    @Transactional(readOnly = true)
    public Optional<AppraisalTransaction> findByRef(String transactionRef) {
        return transactionRepository.findByTransactionRef(transactionRef);
    }

    /**
     * Create a new transaction, optionally as a revision of an existing one.
     *
     * @param amcCode      AMC identifier (name or code from the manifest)
     * @param orderNumber  AMC's order/loan number
     * @param address      Property address
     * @param client       Java Client entity owning the transaction
     * @param revisedFromRef transaction_ref of the transaction being revised (null = new order)
     * @param slaDueAt     Optional SLA deadline from the manifest
     */
    @Transactional
    public AppraisalTransaction createTransaction(
            String amcCode,
            String orderNumber,
            String address,
            Client client,
            String revisedFromRef,
            LocalDateTime slaDueAt) {

        AppraisalTransaction tx = new AppraisalTransaction();
        tx.setAmcCode(amcCode);
        tx.setOrderNumber(orderNumber);
        tx.setPropertyAddress(address);
        tx.setClient(client);
        tx.setStatus(TransactionStatus.RECEIVED);
        // Manifest SLA wins; otherwise default the turnaround deadline to
        // received-time + 48h (configurable via shal.sla.default-hours).
        tx.setSlaDueAt(slaDueAt != null ? slaDueAt : AppTime.now().plusHours(defaultSlaHours));

        if (revisedFromRef != null && !revisedFromRef.isBlank()) {
            transactionRepository.findByTransactionRef(revisedFromRef).ifPresent(original -> {
                tx.setRevisedFrom(original);
                // Revision number is one more than the transaction we are revising.
                tx.setRevisionNumber(original.getRevisionNumber() + 1);
            });
        }

        // Generate a stable transaction reference: AMC-ORDER-YYYYMMDD[-rN]
        String ref = buildRef(amcCode, orderNumber, tx.getRevisionNumber());
        tx.setTransactionRef(ref);

        AppraisalTransaction saved = transactionRepository.save(tx);
        log.info("Transaction created: ref={} amc={} order={} revision={}",
                saved.getTransactionRef(), amcCode, orderNumber, saved.getRevisionNumber());
        return saved;
    }

    /**
     * Link a batch to an existing transaction and advance transaction status to SUBMITTED.
     */
    @Transactional
    public void linkBatchToTransaction(Long batchId, Long transactionId) {
        batchRepository.findById(batchId).ifPresent(batch -> {
            transactionRepository.findById(transactionId).ifPresent(tx -> {
                batch.setTransaction(tx);
                if (tx.getStatus() == TransactionStatus.RECEIVED
                        || tx.getStatus() == TransactionStatus.AWAITING_REVISION) {
                    tx.setStatus(TransactionStatus.SUBMITTED);
                    tx.setSubmittedAt(AppTime.now());
                    transactionRepository.save(tx);
                }
                log.info("Batch {} linked to transaction {}", batchId, tx.getTransactionRef());
            });
        });
    }

    /**
     * Called when a batch under this transaction is COMPLETED (all rules pass or reviewer accepted).
     * Moves the transaction to RESOLVED and records the closure timestamp.
     */
    @Transactional
    public void onBatchCompleted(Long batchId) {
        batchRepository.findById(batchId).ifPresent(batch -> {
            AppraisalTransaction tx = batch.getTransaction();
            if (tx == null) return;
            tx.setStatus(TransactionStatus.RESOLVED);
            tx.setClosedAt(AppTime.now());
            transactionRepository.save(tx);
            log.info("Transaction {} resolved via batch {}", tx.getTransactionRef(), batchId);
        });
    }

    /**
     * Called when a rejection is sent to the AMC.
     * Moves the transaction to AWAITING_REVISION and records the sent timestamp.
     */
    @Transactional
    public void onRejectionSent(Long transactionId) {
        transactionRepository.findById(transactionId).ifPresent(tx -> {
            tx.setStatus(TransactionStatus.AWAITING_REVISION);
            tx.setRevisionSentAt(AppTime.now());
            transactionRepository.save(tx);
            log.info("Transaction {} awaiting revision", tx.getTransactionRef());
        });
    }

    /**
     * Manually abandon a transaction (AMC non-responsive past SLA).
     */
    @Transactional
    public void abandonTransaction(Long transactionId) {
        transactionRepository.findById(transactionId).ifPresent(tx -> {
            tx.setStatus(TransactionStatus.ABANDONED);
            tx.setClosedAt(AppTime.now());
            transactionRepository.save(tx);
            log.info("Transaction {} abandoned", tx.getTransactionRef());
        });
    }

    /** Status counts for the dashboard. */
    @Transactional(readOnly = true)
    public Map<String, Long> statusCounts() {
        Map<String, Long> counts = new java.util.LinkedHashMap<>();
        for (TransactionStatus s : TransactionStatus.values()) {
            counts.put(s.name(), 0L);
        }
        for (Object[] row : transactionRepository.countByStatus()) {
            counts.put(((TransactionStatus) row[0]).name(), (Long) row[1]);
        }
        return counts;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private String buildRef(String amcCode, String orderNumber, int revision) {
        String base = normalize(amcCode) + "-" + normalize(orderNumber) + "-"
                + LocalDateTime.now().toLocalDate().toString().replace("-", "");
        return revision == 0 ? base : base + "-r" + revision;
    }

    private String normalize(String s) {
        if (s == null || s.isBlank()) return "UNKNOWN";
        String clean = s.trim().toUpperCase().replaceAll("[^A-Z0-9]", "");
        return clean.substring(0, Math.min(clean.length(), 20));
    }
}
