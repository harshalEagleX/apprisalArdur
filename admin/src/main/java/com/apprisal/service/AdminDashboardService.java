package com.apprisal.service;

import com.apprisal.entity.*;
import com.apprisal.repository.BatchFileRepository;
import com.apprisal.repository.BatchRepository;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Service for generating dashboard metrics and statistics.
 */
@Service
public class AdminDashboardService {

        private final BatchRepository batchRepository;
        private final BatchFileRepository batchFileRepository;
        private final UserService userService;
        private final ClientService clientService;

        public AdminDashboardService(BatchRepository batchRepository,
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


}
