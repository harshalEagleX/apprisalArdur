package com.apprisal.controller;

import com.apprisal.common.entity.Batch;
import com.apprisal.common.entity.Client;
import com.apprisal.common.entity.User;
import com.apprisal.user.service.DashboardService;
import com.apprisal.batch.service.BatchService;
import com.apprisal.common.service.AuditLogService;
import com.apprisal.common.security.UserPrincipal;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;
import org.springframework.lang.NonNull;

import java.util.Map;

/**
 * Controller for client dashboard and batch management.
 */
@Controller
@RequestMapping("/client")
public class ClientController {

    private final DashboardService dashboardService;
    private final BatchService batchService;
    private final AuditLogService auditLogService;

    public ClientController(DashboardService dashboardService,
            BatchService batchService,
            AuditLogService auditLogService) {
        this.dashboardService = dashboardService;
        this.batchService = batchService;
        this.auditLogService = auditLogService;
    }

    @GetMapping("/dashboard")
    public String dashboard(Model model, @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();
        Client client = user.getClient();

        if (client == null) {
            model.addAttribute("error", "No client organization assigned. Please contact administrator.");
            model.addAttribute("user", user);
            return "client/dashboard";
        }

        Map<String, Object> metrics = dashboardService.getClientDashboard(client.getId());
        model.addAttribute("metrics", metrics);
        model.addAttribute("user", user);
        model.addAttribute("client", client);
        model.addAttribute("currentPage", "dashboard");
        return "client/dashboard";
    }

    @GetMapping("/upload")
    public String uploadPage(Model model, @AuthenticationPrincipal UserPrincipal principal) {
        model.addAttribute("user", principal.getUser());
        model.addAttribute("currentPage", "upload");
        return "client/upload";
    }

    @PostMapping("/upload")
    public String uploadBatch(@RequestParam MultipartFile file,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        User user = principal.getUser();
        Client client = user.getClient();

        if (client == null) {
            redirectAttributes.addFlashAttribute("error", "No client organization assigned");
            return "redirect:/client/dashboard";
        }

        if (file.isEmpty()) {
            redirectAttributes.addFlashAttribute("error", "Please select a file to upload");
            return "redirect:/client/upload";
        }

        String filename = file.getOriginalFilename();
        if (filename == null || !filename.toLowerCase().endsWith(".zip")) {
            redirectAttributes.addFlashAttribute("error", "Please upload a ZIP file");
            return "redirect:/client/upload";
        }

        try {
            Batch batch = batchService.createFromZip(file, client, user);
            auditLogService.logEntity(user, "BATCH_UPLOADED", "Batch", batch.getId());
            redirectAttributes.addFlashAttribute("success",
                    "Batch '" + batch.getParentBatchId() + "' uploaded successfully with " +
                            batch.getFiles().size() + " files");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", "Upload failed: " + e.getMessage());
        }

        return "redirect:/client/dashboard";
    }

    @GetMapping("/batches")
    public String batches(Model model,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size,
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();
        Client client = user.getClient();

        if (client == null) {
            model.addAttribute("error", "No client organization assigned");
            model.addAttribute("user", user);
            return "client/batches";
        }

        Page<Batch> batches = batchService.findByClientId(client.getId(),
                PageRequest.of(page, size, Sort.by("createdAt").descending()));

        model.addAttribute("batches", batches);
        model.addAttribute("user", user);
        model.addAttribute("client", client);
        model.addAttribute("currentPage", "batches");
        return "client/batches";
    }

    @GetMapping("/batches/{id}")
    public String batchDetails(@PathVariable @NonNull Long id,
            Model model,
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();

        Batch batch = batchService.findById(id)
                .orElse(null);

        if (batch == null) {
            model.addAttribute("error", "Batch not found");
            return "redirect:/client/batches";
        }

        // Security check - ensure batch belongs to user's client
        Client userClient = user.getClient();
        if (userClient == null || !batch.getClient().getId().equals(userClient.getId())) {
            model.addAttribute("error", "Access denied");
            return "redirect:/client/batches";
        }

        // Calculate file counts in single pass for efficiency
        var files = batch.getFiles();
        long appraisalCount = 0, engagementCount = 0, completedFiles = 0;
        for (var f : files) {
            if (f.getFileType() == com.apprisal.common.entity.FileType.APPRAISAL)
                appraisalCount++;
            else if (f.getFileType() == com.apprisal.common.entity.FileType.ENGAGEMENT)
                engagementCount++;
            if (f.getStatus() == com.apprisal.common.entity.FileStatus.COMPLETED)
                completedFiles++;
        }

        model.addAttribute("batch", batch);
        model.addAttribute("user", user);
        model.addAttribute("appraisalCount", appraisalCount);
        model.addAttribute("engagementCount", engagementCount);
        model.addAttribute("completedFiles", completedFiles);
        model.addAttribute("currentPage", "batches");
        return "client/batch-details";
    }
}
