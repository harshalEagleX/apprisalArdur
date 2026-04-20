package com.apprisal.service;

import com.apprisal.entity.*;
import com.apprisal.repository.BatchFileRepository;
import com.apprisal.repository.BatchRepository;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class ClientDashboardService {

    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;

    public ClientDashboardService(BatchRepository batchRepository, BatchFileRepository batchFileRepository) {
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
    }

    public Map<String, Object> getClientDashboard(Long clientId) {
        Map<String, Object> metrics = new HashMap<>();

        // Batch counts
        metrics.put("totalBatches", batchRepository.countByClientId(clientId));
        metrics.put("uploaded", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.UPLOADED));
        metrics.put("validating", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.VALIDATING));
        metrics.put("pendingOcr", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.OCR_PENDING));
        metrics.put("processingOcr", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.OCR_PROCESSING));
        metrics.put("pendingReview", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.REVIEW_PENDING));
        metrics.put("inReview", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.IN_REVIEW));
        metrics.put("completed", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.COMPLETED));
        metrics.put("errors", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.ERROR));

        // File counts
        metrics.put("totalFiles", batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.PENDING) +
                batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.PROCESSING) +
                batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.COMPLETED) +
                batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.ERROR));
        metrics.put("filesCompleted", batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.COMPLETED));
        metrics.put("filesPending", batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.PENDING));
        metrics.put("filesProcessing", batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.PROCESSING));

        // Recent batches
        List<Batch> recentBatches = batchRepository.findTop5ByClientIdOrderByCreatedAtDesc(clientId);
        metrics.put("recentBatches", recentBatches);

        return metrics;
    }
}
