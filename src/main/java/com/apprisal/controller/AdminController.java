package com.apprisal.controller;

import com.apprisal.entity.Client;
import com.apprisal.entity.Role;
import com.apprisal.entity.User;
import com.apprisal.service.*;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;
import org.springframework.lang.NonNull;

import java.util.List;
import java.util.Map;

/**
 * Controller for admin dashboard and management pages.
 */
@Controller
@RequestMapping("/admin")
public class AdminController {

    private final DashboardService dashboardService;
    private final UserService userService;
    private final ClientService clientService;
    private final BatchService batchService;
    private final AuditLogService auditLogService;
    private final QCProcessingService qcProcessingService;

    public AdminController(DashboardService dashboardService,
            UserService userService,
            ClientService clientService,
            BatchService batchService,
            AuditLogService auditLogService,
            QCProcessingService qcProcessingService) {
        this.dashboardService = dashboardService;
        this.userService = userService;
        this.clientService = clientService;
        this.batchService = batchService;
        this.auditLogService = auditLogService;
        this.qcProcessingService = qcProcessingService;
    }

    @GetMapping("/dashboard")
    public String dashboard(Model model, @AuthenticationPrincipal UserPrincipal principal) {
        Map<String, Object> metrics = dashboardService.getAdminDashboard();
        model.addAttribute("metrics", metrics);
        model.addAttribute("user", principal.getUser());
        model.addAttribute("recentLogs", auditLogService.getRecentLogs());
        model.addAttribute("currentPage", "dashboard");
        return "admin/dashboard";
    }

    @GetMapping("/users")
    public String users(Model model,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size,
            @AuthenticationPrincipal UserPrincipal principal) {
        Page<User> users = userService.findAll(PageRequest.of(page, size, Sort.by("id").descending()));
        List<Client> clients = clientService.findAll();

        model.addAttribute("users", users);
        model.addAttribute("clients", clients);
        model.addAttribute("roles", Role.values());
        model.addAttribute("user", principal.getUser());
        model.addAttribute("currentPage", "users");
        return "admin/users";
    }

    @PostMapping("/users/create")
    public String createUser(@RequestParam String username,
            @RequestParam String password,
            @RequestParam Role role,
            @RequestParam(required = false) String email,
            @RequestParam(required = false) String fullName,
            @RequestParam(required = false) Long clientId,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        try {
            Client client = clientId != null ? clientService.findById(clientId).orElse(null) : null;
            userService.create(username, password, role, email, fullName, client);
            auditLogService.logSimple(principal.getUser(), "USER_CREATED");
            redirectAttributes.addFlashAttribute("success", "User created successfully");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }
        return "redirect:/admin/users";
    }

    @PostMapping("/users/{id}/update")
    public String updateUser(@PathVariable @NonNull Long id,
            @RequestParam(required = false) String email,
            @RequestParam(required = false) String fullName,
            @RequestParam Role role,
            @RequestParam(required = false) Long clientId,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        try {
            Client client = clientId != null ? clientService.findById(clientId).orElse(null) : null;
            userService.update(id, email, fullName, role, client);
            auditLogService.logEntity(principal.getUser(), "USER_UPDATED", "User", id);
            redirectAttributes.addFlashAttribute("success", "User updated successfully");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }
        return "redirect:/admin/users";
    }

    @PostMapping("/users/{id}/delete")
    public String deleteUser(@PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        try {
            userService.delete(id);
            auditLogService.logEntity(principal.getUser(), "USER_DELETED", "User", id);
            redirectAttributes.addFlashAttribute("success", "User deleted successfully");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }
        return "redirect:/admin/users";
    }

    @GetMapping("/batches")
    public String batches(Model model,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size,
            @AuthenticationPrincipal UserPrincipal principal) {
        var batches = batchService.findAll(PageRequest.of(page, size, Sort.by("createdAt").descending()));
        var reviewers = userService.findByRole(Role.REVIEWER);

        model.addAttribute("batches", batches);
        model.addAttribute("reviewers", reviewers);
        model.addAttribute("user", principal.getUser());
        model.addAttribute("currentPage", "batches");
        return "admin/batches";
    }

    @PostMapping("/batches/{id}/assign")
    public String assignReviewer(@PathVariable @NonNull Long id,
            @RequestParam @NonNull Long reviewerId,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        try {
            User reviewer = userService.findById(reviewerId)
                    .orElseThrow(() -> new IllegalArgumentException("Reviewer not found"));
            batchService.assignReviewer(id, reviewer);
            auditLogService.logEntity(principal.getUser(), "BATCH_ASSIGNED", "Batch", id);
            redirectAttributes.addFlashAttribute("success", "Batch assigned to reviewer");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }
        return "redirect:/admin/batches";
    }

    @PostMapping("/batches/{id}/process-qc")
    public String processQC(@PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        try {
            qcProcessingService.processBatch(id);
            auditLogService.logEntity(principal.getUser(), "QC_PROCESSING_TRIGGERED", "Batch", id);
            redirectAttributes.addFlashAttribute("success", "QC processing started for batch");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", "QC processing failed: " + e.getMessage());
        }
        return "redirect:/admin/batches";
    }

    @GetMapping("/batches/{id}")
    public String batchDetails(@PathVariable @NonNull Long id,
            Model model,
            @AuthenticationPrincipal UserPrincipal principal) {
        return batchService.findById(id)
                .map(batch -> {
                    model.addAttribute("batch", batch);
                    model.addAttribute("user", principal.getUser());
                    model.addAttribute("currentPage", "batches");
                    return "admin/batch-details";
                })
                .orElse("redirect:/admin/batches");
    }

    @PostMapping("/batches/{id}/delete")
    public String deleteBatch(@PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        try {
            batchService.deleteBatch(id);
            auditLogService.logEntity(principal.getUser(), "BATCH_DELETED", "Batch", id);
            redirectAttributes.addFlashAttribute("success", "Batch deleted successfully");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", "Failed to delete batch: " + e.getMessage());
        }
        return "redirect:/admin/batches";
    }

    @GetMapping("/clients")
    public String clients(Model model, @AuthenticationPrincipal UserPrincipal principal) {
        List<Client> clients = clientService.findAll();
        model.addAttribute("clients", clients);
        model.addAttribute("user", principal.getUser());
        model.addAttribute("currentPage", "clients");
        return "admin/clients";
    }

    @PostMapping("/clients/create")
    public String createClient(@RequestParam String name,
            @RequestParam String code,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        try {
            clientService.create(name, code);
            auditLogService.logSimple(principal.getUser(), "CLIENT_CREATED");
            redirectAttributes.addFlashAttribute("success", "Client created successfully");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }
        return "redirect:/admin/clients";
    }

    @GetMapping("/audit-logs")
    public String auditLogs(Model model,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @AuthenticationPrincipal UserPrincipal principal) {
        // For now, get all logs (can add filtering later)
        model.addAttribute("user", principal.getUser());
        model.addAttribute("recentLogs", auditLogService.getRecentLogs());
        model.addAttribute("currentPage", "audit-logs");
        return "admin/audit-logs";
    }
}
