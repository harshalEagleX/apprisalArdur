package com.apprisal.service;

import com.apprisal.entity.*;
import com.apprisal.repository.BatchRepository;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class ReviewerDashboardService {

    private final BatchRepository batchRepository;

    public ReviewerDashboardService(BatchRepository batchRepository) {
        this.batchRepository = batchRepository;
    }

    public Map<String, Object> getReviewerDashboard(Long reviewerId) {
        Map<String, Object> metrics = new HashMap<>();

        long pendingReview = batchRepository.countByAssignedReviewerIdAndStatus(reviewerId, BatchStatus.REVIEW_PENDING);
        long inReview = batchRepository.countByAssignedReviewerIdAndStatus(reviewerId, BatchStatus.IN_REVIEW);
        long completed = batchRepository.countByAssignedReviewerIdAndStatus(reviewerId, BatchStatus.COMPLETED);

        metrics.put("pendingReview", pendingReview);
        metrics.put("inReview", inReview);
        metrics.put("completed", completed);

        metrics.put("assignedBatches", pendingReview + inReview);

        List<Batch> allAssignedBatches = batchRepository.findByAssignedReviewerId(reviewerId);
        long totalFiles = allAssignedBatches.stream()
                .filter(b -> b.getFiles() != null)
                .mapToLong(b -> b.getFiles().size())
                .sum();
        metrics.put("totalFiles", totalFiles);

        return metrics;
    }
}
