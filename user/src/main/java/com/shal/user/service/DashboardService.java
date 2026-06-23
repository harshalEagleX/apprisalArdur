package com.shal.user.service;

import com.shal.common.entity.*;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.repository.BatchRepository;
import com.shal.common.repository.QCResultRepository;
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
        private final QCResultRepository qcResultRepository;
        private final UserService userService;
        private final ClientService clientService;

        public DashboardService(BatchRepository batchRepository,
                        BatchFileRepository batchFileRepository,
                        QCResultRepository qcResultRepository,
                        UserService userService,
                        ClientService clientService) {
                this.batchRepository = batchRepository;
                this.batchFileRepository = batchFileRepository;
                this.qcResultRepository = qcResultRepository;
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

                // Batch counts
                metrics.put("totalBatches", batchRepository.count());
                metrics.put("pendingOcr", batchRepository.countByStatus(BatchStatus.QC_PROCESSING));
                metrics.put("pendingReview", qcResultRepository.countPendingReviewerWork());
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
                        long activeCount = qcResultRepository.countPendingReviewerWorkForReviewer(reviewer.getId());
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

                // Batch counts (used for admin viewing a specific client's work)
                metrics.put("totalBatches", batchRepository.countByClientId(clientId));
                metrics.put("uploaded", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.UPLOADED));
                metrics.put("validating", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.VALIDATING));
                metrics.put("qcProcessing", batchRepository.countByClientIdAndStatus(clientId, BatchStatus.QC_PROCESSING));
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
                long pendingReview = qcResultRepository.countPendingReviewerWorkForReviewer(reviewerId);
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
