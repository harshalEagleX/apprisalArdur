package com.apprisal.common.service;

import com.apprisal.common.entity.*;
import com.apprisal.common.repository.BusinessEventRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.ObjectMapper;

import java.util.Map;

@Service
public class BusinessEventService {

    private static final Logger log = LoggerFactory.getLogger(BusinessEventService.class);

    private final BusinessEventRepository repository;
    private final ObjectMapper objectMapper;
    private final TransactionTemplate transactionTemplate;

    public BusinessEventService(BusinessEventRepository repository,
            ObjectMapper objectMapper,
            PlatformTransactionManager transactionManager) {
        this.repository = repository;
        this.objectMapper = objectMapper;
        this.transactionTemplate = new TransactionTemplate(transactionManager);
        this.transactionTemplate.setPropagationBehaviorName("PROPAGATION_REQUIRES_NEW");
    }

    public void record(String eventType, User actor, String sourceLayer, String outcome,
                       String entityType, Long entityId, Long batchId, Long batchFileId,
                       Long qcResultId, Long ruleResultId, Map<String, ?> payload) {
        try {
            transactionTemplate.executeWithoutResult(status -> {
                BusinessEvent event = new BusinessEvent();
                event.setEventType(eventType);
                event.setActor(actor);
                event.setActorRole(actor != null && actor.getRole() != null ? actor.getRole().name() : null);
                event.setSourceLayer(sourceLayer);
                event.setOutcome(outcome);
                event.setEntityType(entityType);
                event.setEntityId(entityId);
                event.setBatchId(batchId);
                event.setBatchFileId(batchFileId);
                event.setQcResultId(qcResultId);
                event.setRuleResultId(ruleResultId);
                event.setCorrelationId(resolveCorrelationId(batchId, batchFileId, qcResultId, ruleResultId));
                event.setPayloadJson(toPayloadJson(eventType, payload));
                repository.saveAndFlush(event);
            });
        } catch (Exception e) {
            log.error("Business event capture failed for eventType={}, entityType={}, entityId={}: {}",
                    eventType, entityType, entityId, e.getMessage(), e);
        }
    }

    public void batchEvent(String eventType, User actor, Batch batch, String outcome, Map<String, ?> payload) {
        record(eventType, actor, "java", outcome, "Batch", batch != null ? batch.getId() : null,
                batch != null ? batch.getId() : null, null, null, null, payload);
    }

    public void qcEvent(String eventType, User actor, QCResult qcResult, String outcome, Map<String, ?> payload) {
        BatchFile file = qcResult != null ? qcResult.getBatchFile() : null;
        Batch batch = file != null ? file.getBatch() : null;
        record(eventType, actor, "java", outcome, "QCResult", qcResult != null ? qcResult.getId() : null,
                batch != null ? batch.getId() : null,
                file != null ? file.getId() : null,
                qcResult != null ? qcResult.getId() : null,
                null,
                payload);
    }

    private String resolveCorrelationId(Long batchId, Long batchFileId, Long qcResultId, Long ruleResultId) {
        String correlationId = MDC.get("correlationId");
        if (correlationId != null && !correlationId.isBlank()) {
            return truncate(correlationId, 64);
        }
        if (batchId != null) {
            return "batch:" + batchId;
        }
        if (qcResultId != null) {
            return "qc:" + qcResultId;
        }
        if (batchFileId != null) {
            return "file:" + batchFileId;
        }
        if (ruleResultId != null) {
            return "rule:" + ruleResultId;
        }
        return null;
    }

    private String toPayloadJson(String eventType, Map<String, ?> payload) {
        if (payload == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (Exception e) {
            log.warn("Could not serialize payload for business event {}: {}", eventType, e.getMessage());
            return null;
        }
    }

    private String truncate(String value, int maxLength) {
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }
}
