package com.shal.common.repository;

import com.shal.common.entity.DocumentMatch;
import com.shal.common.entity.FileType;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface DocumentMatchRepository extends JpaRepository<DocumentMatch, Long> {
    @EntityGraph(attributePaths = {"appraisalFile", "supportingFile"})
    Optional<DocumentMatch> findByAppraisalFile_IdAndSupportingFileType(Long appraisalFileId, FileType supportingFileType);

    @EntityGraph(attributePaths = {"appraisalFile", "supportingFile"})
    List<DocumentMatch> findByAppraisalFile_Batch_Id(Long batchId);

    @EntityGraph(attributePaths = {"appraisalFile", "supportingFile"})
    List<DocumentMatch> findByAppraisalFile_Id(Long appraisalFileId);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
        DELETE FROM DocumentMatch dm
        WHERE dm.appraisalFile.batch.id = :batchId
           OR dm.supportingFile.batch.id = :batchId
        """)
    int deleteByBatchId(@Param("batchId") Long batchId);
}
