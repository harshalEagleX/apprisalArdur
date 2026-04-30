package com.apprisal.common.repository;

import com.apprisal.common.entity.BatchFile;
import com.apprisal.common.entity.FileStatus;
import com.apprisal.common.entity.FileType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface BatchFileRepository extends JpaRepository<BatchFile, Long> {

    List<BatchFile> findByBatchId(Long batchId);

    List<BatchFile> findByBatchIdAndFileType(Long batchId, FileType fileType);

    List<BatchFile> findByBatchIdAndStatus(Long batchId, FileStatus status);

    /**
     * Find files by batch, orderId, and type - for matching appraisal with
     * engagement. Returns List to handle possible duplicates.
     */
    List<BatchFile> findByBatchIdAndOrderIdAndFileType(Long batchId, String orderId, FileType fileType);

    /**
     * Find all files with a specific orderId in a batch.
     */
    List<BatchFile> findByBatchIdAndOrderId(Long batchId, String orderId);

    @Query("SELECT COUNT(bf) FROM BatchFile bf WHERE bf.batch.id = :batchId")
    long countByBatchId(@Param("batchId") Long batchId);

    long countByBatchIdAndFileType(Long batchId, FileType fileType);

    @Query("SELECT COUNT(bf) FROM BatchFile bf WHERE bf.batch.id = :batchId AND bf.status = :status")
    long countByBatchIdAndStatus(@Param("batchId") Long batchId, @Param("status") FileStatus status);

    @Query("SELECT COUNT(bf) FROM BatchFile bf WHERE bf.batch.client.id = :clientId AND bf.status = :status")
    long countByClientIdAndStatus(@Param("clientId") Long clientId, @Param("status") FileStatus status);
}
