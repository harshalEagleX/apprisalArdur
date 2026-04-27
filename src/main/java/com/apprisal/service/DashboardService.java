package com.apprisal.service;

import com.apprisal.entity.*;
import com.apprisal.repository.BatchFileRepository;
import com.apprisal.repository.BatchRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Service for generating dashboard metrics and statistics.
 */
@Service
@Transactional(readOnly = true)
public class DashboardService {

        private final BatchRepository batchRepository;
        private final BatchFileRepository batchFileRepository;
        private final UserService userService;
        private final ClientService clientService;

        public DashboardService(BatchRepository batchRepository,
                        BatchFileRepository batchFileRepository,
                        UserService userService,
                        ClientService clientService) {
                this.batchRepository = batchRepository;
                this.batchFileRepository = batchFileRepository;
                this.userService = userService;
                this.clientService = clientService;
        }

        /**
         * Get admin dashboard metrics.
         */
        public Map<String, Object> getAdminDashboard() {
                Map<String, Object> metrics = new HashMap<>();

                // User counts
                metrics.put("totalUsers", userService.count());
                metrics.put("adminCount", userService.countByRole(Role.ADMIN));
                metrics.put("reviewerCount", userService.countByRole(Role.REVIEWER));
                metrics.put("clientCount", userService.countByRole(Role.CLIENT));

                // Batch counts
                metrics.put("totalBatches", batchRepository.count());
                metrics.put("pendingOcr", batchRepository.countByStatus(BatchStatus.OCR_PENDING));
                metrics.put("processingOcr", batchRepository.countByStatus(BatchStatus.OCR_PROCESSING));
                metrics.put("pendingReview", batchRepository.countByStatus(BatchStatus.REVIEW_PENDING));
                metrics.put("inReview", batchRepository.countByStatus(BatchStatus.IN_REVIEW));
                metrics.put("completed", batchRepository.countByStatus(BatchStatus.COMPLETED));
                metrics.put("errors", batchRepository.countByStatus(BatchStatus.ERROR));

                // Client organization count
                metrics.put("clientOrganizations", clientService.count());

                // Recent batches - efficient TopN query
                List<Batch> recentBatches = batchRepository.findTop10ByOrderByCreatedAtDesc();
                metrics.put("recentBatches", recentBatches);

                // Reviewers with workload
                List<User> reviewers = userService.findByRole(Role.REVIEWER);
                Map<Long, Long> reviewerWorkload = new HashMap<>();
                for (User reviewer : reviewers) {
                        long activeCount = batchRepository.countByAssignedReviewerIdAndStatus(reviewer.getId(),
                                        BatchStatus.IN_REVIEW);
                        reviewerWorkload.put(reviewer.getId(), activeCount);
                }
                metrics.put("reviewerWorkload", reviewerWorkload);
                metrics.put("reviewers", reviewers);

                return metrics;
        }

        /**
         * Get client dashboard metrics.
         */
        public Map<String, Object> getClientDashboard(Long clientId) {
                Map<String, Object> metrics = new HashMap<>();

                // Batch counts
                metrics.put("totalBatches", batchRepository.countByClientId(clientId));
                metrics.put("uploaded", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.UPLOADED));
                metrics.put("validating", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.VALIDATING));
                metrics.put("pendingOcr", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.OCR_PENDING));
                metrics.put("processingOcr",
                                batchRepository.countByClientIdAndStatus(clientId, BatchStatus.OCR_PROCESSING));
                metrics.put("pendingReview",
                                batchRepository.countByClientIdAndStatus(clientId, BatchStatus.REVIEW_PENDING));
                metrics.put("inReview", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.IN_REVIEW));
                metrics.put("completed", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.COMPLETED));
                metrics.put("errors", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.ERROR));

                // File counts
                metrics.put("totalFiles", batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.PENDING) +
                                batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.PROCESSING) +
                                batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.COMPLETED) +
                                batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.ERROR));
                metrics.put("filesCompleted",
                                batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.COMPLETED));
                metrics.put("filesPending", batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.PENDING));
                metrics.put("filesProcessing",
                                batchFileRepository.countByClientIdAndStatus(clientId, FileStatus.PROCESSING));

                // Recent batches - efficient TopN query
                List<Batch> recentBatches = batchRepository.findTop5ByClientIdOrderByCreatedAtDesc(clientId);
                metrics.put("recentBatches", recentBatches);

                return metrics;
        }

        /**
         * Get reviewer dashboard metrics.
         */
        public Map<String, Object> getReviewerDashboard(Long reviewerId) {
                Map<String, Object> metrics = new HashMap<>();

                // Assigned batch counts
                long pendingReview = batchRepository.countByAssignedReviewerIdAndStatus(reviewerId,
                                BatchStatus.REVIEW_PENDING);
                long inReview = batchRepository.countByAssignedReviewerIdAndStatus(reviewerId, BatchStatus.IN_REVIEW);
                long completed = batchRepository.countByAssignedReviewerIdAndStatus(reviewerId, BatchStatus.COMPLETED);

                metrics.put("pendingReview", pendingReview);
                metrics.put("inReview", inReview);
                metrics.put("completed", completed);

                // Total assigned batches count (for the stat card)
                metrics.put("assignedBatches", pendingReview + inReview);

                // Calculate total files across all assigned batches
                List<Batch> allAssignedBatches = batchRepository.findByAssignedReviewerId(reviewerId);
                long totalFiles = allAssignedBatches.stream()
                                .filter(b -> b.getFiles() != null)
                                .mapToLong(b -> b.getFiles().size())
                                .sum();
                metrics.put("totalFiles", totalFiles);

                return metrics;
        }
}
