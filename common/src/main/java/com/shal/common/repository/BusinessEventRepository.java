package com.shal.common.repository;

import com.shal.common.entity.BusinessEvent;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface BusinessEventRepository extends JpaRepository<BusinessEvent, Long> {

    @Query("SELECT be FROM BusinessEvent be WHERE be.batchId IN :batchIds ORDER BY be.batchId, be.occurredAt ASC")
    List<BusinessEvent> findByBatchIdIn(@Param("batchIds") List<Long> batchIds);

    @Query("SELECT be FROM BusinessEvent be WHERE be.qcResultId IN :qcResultIds ORDER BY be.qcResultId, be.occurredAt ASC")
    List<BusinessEvent> findByQcResultIdIn(@Param("qcResultIds") List<Long> qcResultIds);

    /**
     * All events directly associated with a batch file, ordered chronologically.
     * Powers the per-file history/audit timeline in the batch detail view.
     */
    @Query("SELECT be FROM BusinessEvent be WHERE be.batchFileId = :batchFileId ORDER BY be.occurredAt ASC")
    List<BusinessEvent> findByBatchFileId(@Param("batchFileId") Long batchFileId);

    /**
     * Batch-level lifecycle events (no specific file), for supplementing the
     * file timeline with upload and QC-start context from the parent batch.
     */
    @Query("""
        SELECT be FROM BusinessEvent be
        WHERE be.batchId = :batchId
          AND be.batchFileId IS NULL
          AND be.eventType IN ('BATCH_CREATED','BATCH_QC_STARTED','BATCH_QC_COMPLETED','BATCH_QC_QUEUED','BATCH_QC_FAILED','BATCH_QC_CANCELLED')
        ORDER BY be.occurredAt ASC
        """)
    List<BusinessEvent> findBatchLifecycleEvents(@Param("batchId") Long batchId);
}
