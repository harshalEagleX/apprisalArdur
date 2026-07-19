package com.shal.common.service;

import com.shal.common.entity.AppraisalTransaction;
import com.shal.common.entity.BatchFile;
import com.shal.common.entity.FileStatus;
import com.shal.common.entity.FileType;
import com.shal.common.entity.OrderDocumentStatus;
import com.shal.common.entity.QCResult;
import com.shal.common.repository.AppraisalTransactionRepository;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.repository.QCResultRepository;
import com.shal.common.util.AppTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

/**
 * Computes and persists {@link AppraisalTransaction#getDocumentStatus()} — the
 * Order-owned lifecycle status the design doc calls for. This is written
 * exclusively here, never set directly by a controller, mirroring the
 * existing determineBatchStatus/recomputeBatchStatusFromActiveResults pattern
 * in QCProcessingService but scoped to one Order instead of a whole batch.
 */
@Service
public class OrderStatusService {

    private static final Logger log = LoggerFactory.getLogger(OrderStatusService.class);

    private final BatchFileRepository batchFileRepository;
    private final QCResultRepository qcResultRepository;
    private final AppraisalTransactionRepository appraisalTransactionRepository;

    public OrderStatusService(BatchFileRepository batchFileRepository,
                              QCResultRepository qcResultRepository,
                              AppraisalTransactionRepository appraisalTransactionRepository) {
        this.batchFileRepository = batchFileRepository;
        this.qcResultRepository = qcResultRepository;
        this.appraisalTransactionRepository = appraisalTransactionRepository;
    }

    @Transactional
    public void recompute(AppraisalTransaction order) {
        if (order == null || order.getId() == null) return;

        OrderDocumentStatus computed = compute(order);
        if (computed != order.getDocumentStatus()) {
            log.debug("Order {} documentStatus {} -> {}", order.getTransactionRef(), order.getDocumentStatus(), computed);
            order.setDocumentStatus(computed);
        }
        appraisalTransactionRepository.save(order);
    }

    /**
     * Claim-time transition to {@link OrderDocumentStatus#QC_PROCESSING}. This is the
     * Order-grained analogue of {@code BatchRepository.markQcProcessingIfTriggerable} — the
     * Order (not the Batch) is now the QC coordination unit, so its lifecycle status is what
     * flips when a run starts.
     *
     * <p>Guarded against a double-run only: an order already {@code QC_PROCESSING} is rejected
     * (mirrors {@code markQcProcessingIfTriggerable}'s conditional update). Document
     * <em>completeness</em> is NOT re-checked here — the QC trigger endpoint is the completeness
     * authority (it blocks incomplete/unmatched orders via {@code OrderCompleteness} before
     * claiming), and the stored {@code documentStatus} may lag actual file state. Returns
     * {@code true} only if the claim was taken.
     */
    @Transactional
    public boolean markProcessing(AppraisalTransaction order) {
        if (order == null || order.getId() == null) return false;
        // Atomic conditional UPDATE — the row is the cross-node source of truth for the
        // claim (rows==1 → we won it; rows==0 → another node/thread already holds it).
        // Replaces the old read-then-write, which double-ran the same order across nodes.
        int rows = appraisalTransactionRepository.claimForQcIfNotProcessing(order.getId(), AppTime.now());
        if (rows == 0) {
            log.debug("Order {} already QC_PROCESSING — rejecting duplicate claim", order.getTransactionRef());
            return false;
        }
        // Reflect the committed transition on the in-memory entity for callers that keep using it.
        order.setDocumentStatus(OrderDocumentStatus.QC_PROCESSING);
        return true;
    }

    /** Force an order to {@link OrderDocumentStatus#ERROR} (worker crash / abandon paths). */
    @Transactional
    public void markError(AppraisalTransaction order) {
        if (order == null || order.getId() == null) return;
        order.setDocumentStatus(OrderDocumentStatus.ERROR);
        appraisalTransactionRepository.save(order);
    }

    private OrderDocumentStatus compute(AppraisalTransaction order) {
        List<BatchFile> activeDocs = batchFileRepository.findActiveByOrderId(order.getId());

        boolean hasErrorFile = activeDocs.stream().anyMatch(f -> f.getStatus() == FileStatus.ERROR);
        boolean hasNeedsAssignment = activeDocs.stream().anyMatch(f -> f.getStatus() == FileStatus.NEEDS_ASSIGNMENT);
        Optional<BatchFile> activeAppraisal = activeDocs.stream()
                .filter(f -> f.getFileType() == FileType.APPRAISAL)
                .findFirst();
        // Completeness uses the single shared definition (appraisal PDF + XML + engagement)
        // so the order status can never say READY_FOR_QC while the QC gate refuses to run it.
        java.util.Set<FileType> presentTypes = activeDocs.stream()
                .map(BatchFile::getFileType)
                .collect(java.util.stream.Collectors.toSet());

        if (hasNeedsAssignment) return OrderDocumentStatus.UNMATCHED;
        if (!OrderCompleteness.isComplete(presentTypes)) return OrderDocumentStatus.INCOMPLETE;
        if (hasErrorFile) return OrderDocumentStatus.ERROR;

        BatchFile appraisal = activeAppraisal.get();
        Optional<QCResult> activeResult = qcResultRepository.findActiveByBatchFileId(appraisal.getId());

        if (activeResult.isEmpty()) {
            return appraisal.getStatus() == FileStatus.PROCESSING
                    ? OrderDocumentStatus.QC_PROCESSING
                    : OrderDocumentStatus.READY_FOR_QC;
        }

        QCResult result = activeResult.get();
        if (result.getFinalDecision() != null) return OrderDocumentStatus.COMPLETED;
        if (result.getQcDecision() != null && result.getQcDecision().name().equals("AUTO_PASS")) {
            return OrderDocumentStatus.COMPLETED;
        }
        return OrderDocumentStatus.NEEDS_REVIEW;
    }
}
