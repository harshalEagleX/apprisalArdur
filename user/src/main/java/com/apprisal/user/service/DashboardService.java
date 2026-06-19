package com.apprisal.user.service;

import com.apprisal.common.entity.*;
import com.apprisal.common.repository.BatchFileRepository;
import com.apprisal.common.repository.BatchRepository;
import com.apprisal.common.repository.QCResultRepository;
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

                // Recent batches — project to plain maps so Jackson never sees LAZY
                // associations (files, createdBy) after the transaction closes.
                List<Map<String, Object>> recentBatches = batchRepository.findTop10ByOrderByCreatedAtDesc()
                                .stream()
                                .map(b -> {
                                        Map<String, Object> m = new HashMap<>();
                                        m.put("id",            b.getId());
                                        m.put("parentBatchId", b.getParentBatchId());
                                        m.put("status",        b.getStatus() != null ? b.getStatus().name() : null);
                                        m.put("createdAt",     b.getCreatedAt() != null ? b.getCreatedAt().toString() : null);
                                        m.put("fileCount",     b.getFileCount());
                                        m.put("client", b.getClient() != null
                                                ? Map.of("id", b.getClient().getId(), "name", b.getClient().getName() != null ? b.getClient().getName() : "")
                                                : null);
                                        m.put("assignedReviewer", b.getAssignedReviewer() != null
                                                ? Map.of("id", b.getAssignedReviewer().getId(), "username", b.getAssignedReviewer().getUsername())
                                                : null);
                                        return m;
                                })
                                .collect(java.util.stream.Collectors.toList());
                metrics.put("recentBatches", recentBatches);

                // Reviewers with workload — project to plain maps (avoid LAZY User associations).
                List<User> reviewers = userService.findByRole(Role.REVIEWER);
                Map<Long, Long> reviewerWorkload = new HashMap<>();
                List<Map<String, Object>> reviewerList = new java.util.ArrayList<>();
                for (User reviewer : reviewers) {
                        long activeCount = qcResultRepository.countPendingReviewerWorkForReviewer(reviewer.getId());
                        reviewerWorkload.put(reviewer.getId(), activeCount);
                        Map<String, Object> rv = new HashMap<>();
                        rv.put("id",       reviewer.getId());
                        rv.put("username", reviewer.getUsername());
                        rv.put("fullName", reviewer.getFullName() != null ? reviewer.getFullName() : "");
                        reviewerList.add(rv);
                }
                metrics.put("reviewerWorkload", reviewerWorkload);
                metrics.put("reviewers", reviewerList);

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

                // Recent batches — project to plain maps (same LAZY-safety pattern as admin dashboard).
                List<Map<String, Object>> recentBatches = batchRepository.findTop5ByClientIdOrderByCreatedAtDesc(clientId)
                                .stream()
                                .map(b -> {
                                        Map<String, Object> m = new HashMap<>();
                                        m.put("id",            b.getId());
                                        m.put("parentBatchId", b.getParentBatchId());
                                        m.put("status",        b.getStatus() != null ? b.getStatus().name() : null);
                                        m.put("createdAt",     b.getCreatedAt() != null ? b.getCreatedAt().toString() : null);
                                        m.put("fileCount",     b.getFileCount());
                                        return m;
                                })
                                .collect(java.util.stream.Collectors.toList());
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

                metrics.put("totalFiles", batchFileRepository.countByReviewerId(reviewerId));

                return metrics;
        }
}
