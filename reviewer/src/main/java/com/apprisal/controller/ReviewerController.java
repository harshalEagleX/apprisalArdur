package com.apprisal.controller;

import com.apprisal.entity.*;
import com.apprisal.repository.QCResultRepository;
import com.apprisal.service.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;
import java.util.Objects;
import org.springframework.lang.NonNull;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Controller for reviewer dashboard and batch review workflow.
 */
@Controller
@RequestMapping("/reviewer")
public class ReviewerController {

    private final ReviewerDashboardService dashboardService;
    private final BatchService batchService;
    private final VerificationService verificationService;
    private final QCResultRepository qcResultRepository;

    public ReviewerController(ReviewerDashboardService dashboardService,
            BatchService batchService,
            VerificationService verificationService,
            QCResultRepository qcResultRepository) {
        this.dashboardService = dashboardService;
        this.batchService = batchService;
        this.verificationService = verificationService;
        this.qcResultRepository = qcResultRepository;
    }

    @GetMapping("/dashboard")
    public String dashboard(Model model, @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();
        Map<String, Object> metrics = dashboardService.getReviewerDashboard(user.getId());

        List<Batch> assignedBatches = batchService.findByReviewerId(user.getId());

        model.addAttribute("user", user);
        model.addAttribute("metrics", metrics);
        model.addAttribute("assignedBatches", assignedBatches);
        model.addAttribute("currentPage", "dashboard");

        return "reviewer/dashboard";
    }

    @GetMapping("/batches")
    public String batches(Model model, @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();
        List<Batch> batches = batchService.findByReviewerId(user.getId());

        model.addAttribute("user", user);
        model.addAttribute("batches", batches);
        model.addAttribute("currentPage", "batches");

        return "reviewer/batches";
    }

    /**
     * Queue of batches with TO_VERIFY items waiting for review.
     */
    @GetMapping("/queue")
    public String verificationQueue(Model model, @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();

        // Get all TO_VERIFY QC results
        List<QCResult> pendingVerification = qcResultRepository.findByQcDecision(QCDecision.TO_VERIFY);

        model.addAttribute("user", user);
        model.addAttribute("pendingItems", pendingVerification);
        model.addAttribute("currentPage", "queue");

        return "reviewer/queue";
    }

    @GetMapping("/batches/{id}")
    public String batchDetails(@PathVariable @NonNull Long id,
            Model model,
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();

        Batch batch = batchService.findById(id).orElse(null);
        if (batch == null) {
            return "redirect:/reviewer/batches";
        }

        // Security check
        if (batch.getAssignedReviewer() == null ||
                !batch.getAssignedReviewer().getId().equals(user.getId())) {
            return "redirect:/reviewer/batches";
        }

        // Get QC results for this batch
        List<QCResult> qcResults = qcResultRepository.findByBatchId(id);

        model.addAttribute("user", user);
        model.addAttribute("batch", batch);
        model.addAttribute("qcResults", qcResults);
        model.addAttribute("currentPage", "batches");

        return "reviewer/batch-details";
    }

    /**
     * Verify file page - shows PDF and all QC rules with verification controls.
     */
    @GetMapping("/verify/{qcResultId}")
    public String verifyFile(@PathVariable @NonNull Long qcResultId,
            Model model,
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();

        QCResult qcResult = verificationService.getForVerification(qcResultId);
        // Get ALL rule results for full visibility (not just verification items)
        List<QCRuleResult> allRuleResults = verificationService.getAllRuleResults(qcResultId);

        model.addAttribute("user", user);
        model.addAttribute("qcResult", qcResult);
        model.addAttribute("batchFile", qcResult.getBatchFile());
        model.addAttribute("allRuleResults", allRuleResults);
        model.addAttribute("currentPage", "verify");

        return "reviewer/verify-file";
    }

    /**
     * Submit verification decisions.
     */
    @PostMapping("/verify/{qcResultId}")
    public String submitVerification(@PathVariable @NonNull Long qcResultId,
            @RequestParam Map<String, String> formData,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        User user = Objects.requireNonNull(principal.getUser());

        try {
            // Parse form data into decisions and comments
            Map<Long, Boolean> decisions = new HashMap<>();
            Map<Long, String> comments = new HashMap<>();
            String overallNotes = formData.get("overallNotes");

            for (Map.Entry<String, String> entry : formData.entrySet()) {
                String key = entry.getKey();
                if (key.startsWith("decision_")) {
                    Long ruleId = Long.parseLong(key.replace("decision_", ""));
                    decisions.put(ruleId, "accept".equals(entry.getValue()));
                } else if (key.startsWith("comment_")) {
                    Long ruleId = Long.parseLong(key.replace("comment_", ""));
                    comments.put(ruleId, entry.getValue());
                }
            }

            QCResult result = verificationService.submitVerification(
                    qcResultId, decisions, comments, user, overallNotes);

            // Update batch status if all files verified
            updateBatchStatusAfterVerification(result.getBatchFile().getBatch());

            redirectAttributes.addFlashAttribute("success",
                    "Verification submitted. Final decision: " + result.getFinalDecision());

        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }

        return "redirect:/reviewer/queue";
    }

    /**
     * Quick accept all items.
     */
    @PostMapping("/verify/{qcResultId}/accept-all")
    public String acceptAll(@PathVariable @NonNull Long qcResultId,
            @RequestParam(required = false) String notes,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        User user = Objects.requireNonNull(principal.getUser());

        try {
            QCResult result = verificationService.acceptAll(qcResultId, user, notes);
            updateBatchStatusAfterVerification(result.getBatchFile().getBatch());

            redirectAttributes.addFlashAttribute("success", "All items accepted");

        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }

        return "redirect:/reviewer/queue";
    }

    /**
     * Quick reject.
     */
    @PostMapping("/verify/{qcResultId}/reject")
    public String rejectAll(@PathVariable @NonNull Long qcResultId,
            @RequestParam String reason,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        User user = Objects.requireNonNull(principal.getUser());

        try {
            QCResult result = verificationService.rejectAll(qcResultId, user, reason);
            updateBatchStatusAfterVerification(result.getBatchFile().getBatch());

            redirectAttributes.addFlashAttribute("success", "File rejected");

        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }

        return "redirect:/reviewer/queue";
    }

    @PostMapping("/batches/{id}/start")
    public String startReview(@PathVariable Long id,
            RedirectAttributes redirectAttributes) {

        try {
            batchService.updateStatus(id, BatchStatus.IN_REVIEW);
            redirectAttributes.addFlashAttribute("success", "Review started successfully");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }

        return "redirect:/reviewer/batches/" + id;
    }

    @PostMapping("/batches/{id}/complete")
    public String completeReview(@PathVariable Long id,
            RedirectAttributes redirectAttributes) {

        try {
            batchService.updateStatus(id, BatchStatus.COMPLETED);
            redirectAttributes.addFlashAttribute("success", "Review completed successfully");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }

        return "redirect:/reviewer/dashboard";
    }

    @GetMapping("/completed")
    public String completedBatches(Model model, @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();
        List<Batch> batches = batchService.findByReviewerIdAndStatus(user.getId(), BatchStatus.COMPLETED);

        model.addAttribute("user", user);
        model.addAttribute("batches", batches);
        model.addAttribute("currentPage", "completed");

        return "reviewer/completed";
    }

    /**
     * Update batch status based on all QC results.
     */
    private void updateBatchStatusAfterVerification(Batch batch) {
        List<QCResult> results = qcResultRepository.findByBatchId(batch.getId());

        boolean allVerified = results.stream()
                .allMatch(r -> r.getFinalDecision() != null);

        if (!allVerified) {
            return; // Still have unverified items
        }

        boolean anyFailed = results.stream()
                .anyMatch(r -> r.getFinalDecision() == FinalDecision.FAIL);

        if (anyFailed) {
            batchService.updateStatus(batch.getId(), BatchStatus.REJECTED);
        } else {
            batchService.updateStatus(batch.getId(), BatchStatus.COMPLETED);
        }
    }
}
