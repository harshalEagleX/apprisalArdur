package com.shal.common.service;

import com.shal.common.entity.BatchFile;
import com.shal.common.exception.ResourceNotFoundException;
import com.shal.common.repository.AppraisalTransactionRepository;
import com.shal.common.repository.BatchFileRepository;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;

/**
 * Permanently deletes an Order (AppraisalTransaction) and all of its documents.
 *
 * Hard delete — not recoverable. Every FK dependent of {@code batch_file} and
 * {@code appraisal_transaction} is NO ACTION (no DB cascade), so rows are removed
 * child-first in one transaction, in this order:
 *   doc_stat / processing_metrics / qc_rule_result  →  qc_result  →  document_match
 *   →  batch_file  →  (null out batch.transaction_id & appraisal_transaction.revised_from_id)
 *   →  appraisal_transaction.
 * The physical files are then removed from disk. Verified against the live schema
 * with a rollback dry-run before shipping.
 */
@Service
public class OrderDeletionService {

    private static final Logger log = LoggerFactory.getLogger(OrderDeletionService.class);

    @PersistenceContext
    private EntityManager em;

    private final BatchFileRepository batchFileRepository;
    private final AppraisalTransactionRepository orderRepository;

    public OrderDeletionService(BatchFileRepository batchFileRepository,
                                AppraisalTransactionRepository orderRepository) {
        this.batchFileRepository = batchFileRepository;
        this.orderRepository = orderRepository;
    }

    /** Permanently delete the order and its documents. Returns the number of files removed. */
    @Transactional
    public int hardDeleteOrder(Long orderId) {
        if (!orderRepository.existsById(orderId)) {
            throw new ResourceNotFoundException("Order", "id", orderId);
        }

        List<BatchFile> files = batchFileRepository.findAllByOrderId(orderId);
        List<Long> fileIds = files.stream().map(BatchFile::getId).toList();
        List<String> paths = files.stream()
                .map(BatchFile::getStoragePath).filter(Objects::nonNull).toList();

        if (!fileIds.isEmpty()) {
            exec("DELETE FROM doc_stat WHERE qc_result_id IN (SELECT id FROM qc_result WHERE batch_file_id IN (:ids))", fileIds);
            exec("DELETE FROM processing_metrics WHERE qc_result_id IN (SELECT id FROM qc_result WHERE batch_file_id IN (:ids))", fileIds);
            exec("DELETE FROM qc_rule_result WHERE qc_result_id IN (SELECT id FROM qc_result WHERE batch_file_id IN (:ids))", fileIds);
            exec("UPDATE qc_result SET rerun_of = NULL WHERE rerun_of IN (SELECT id FROM qc_result WHERE batch_file_id IN (:ids))", fileIds);
            exec("DELETE FROM qc_result WHERE batch_file_id IN (:ids)", fileIds);
            exec("DELETE FROM document_match WHERE supporting_file_id IN (:ids) OR appraisal_file_id IN (:ids)", fileIds);
            exec("DELETE FROM batch_file WHERE id IN (:ids)", fileIds);
        }

        em.createNativeQuery("UPDATE batch SET transaction_id = NULL WHERE transaction_id = :oid")
                .setParameter("oid", orderId).executeUpdate();
        em.createNativeQuery("UPDATE appraisal_transaction SET revised_from_id = NULL WHERE revised_from_id = :oid")
                .setParameter("oid", orderId).executeUpdate();
        em.createNativeQuery("DELETE FROM appraisal_transaction WHERE id = :oid")
                .setParameter("oid", orderId).executeUpdate();

        // Remove the physical files from disk (best-effort; the DB is already consistent).
        int removedFromDisk = 0;
        for (String p : paths) {
            try {
                if (Files.deleteIfExists(Path.of(p))) removedFromDisk++;
            } catch (Exception e) {
                log.warn("Order {} delete: could not remove file {}: {}", orderId, p, e.getMessage());
            }
        }
        log.info("Hard-deleted order id={} — {} document row(s), {} file(s) removed from disk",
                orderId, files.size(), removedFromDisk);
        return files.size();
    }

    private void exec(String sql, List<Long> ids) {
        em.createNativeQuery(sql).setParameter("ids", ids).executeUpdate();
    }
}
