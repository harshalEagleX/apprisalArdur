package com.shal.common.repository;

import com.shal.common.entity.BusinessEvent;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface BusinessEventRepository extends JpaRepository<BusinessEvent, Long> {
    List<BusinessEvent> findByBatchIdOrderByOccurredAtAsc(Long batchId);
    List<BusinessEvent> findByQcResultIdOrderByOccurredAtAsc(Long qcResultId);
}
