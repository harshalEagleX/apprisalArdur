package com.apprisal.common.repository;

import com.apprisal.common.entity.BusinessEvent;
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
}
