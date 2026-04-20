package com.apprisal.controller;

import com.apprisal.entity.User;
import com.apprisal.service.UserPrincipal;
import com.apprisal.service.UserService;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Controller;
import java.util.Objects;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

/**
 * Controller for user profile management.
 */
@Controller
@RequestMapping("/profile")
public class ProfileController {

    private final UserService userService;
    private final PasswordEncoder passwordEncoder;

    public ProfileController(UserService userService, PasswordEncoder passwordEncoder) {
        this.userService = userService;
        this.passwordEncoder = passwordEncoder;
    }

    @GetMapping
    public String profile(Model model, @AuthenticationPrincipal UserPrincipal principal) {
        model.addAttribute("user", principal.getUser());
        model.addAttribute("currentPage", "profile");
        return "profile";
    }

    @PostMapping
    public String updateProfile(@RequestParam(required = false) String email,
            @RequestParam(required = false) String fullName,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        try {
            User user = principal.getUser();
            userService.update(Objects.requireNonNull(user.getId()), email, fullName, user.getRole(), user.getClient());
            redirectAttributes.addFlashAttribute("success", "Profile updated successfully");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }
        return "redirect:/profile";
    }

    @PostMapping("/password")
    public String updatePassword(@RequestParam String currentPassword,
            @RequestParam String newPassword,
            @RequestParam String confirmPassword,
            @AuthenticationPrincipal UserPrincipal principal,
            RedirectAttributes redirectAttributes) {
        User user = principal.getUser();

        // Validate current password
        if (!passwordEncoder.matches(currentPassword, user.getPassword())) {
            redirectAttributes.addFlashAttribute("error", "Current password is incorrect");
            return "redirect:/profile";
        }

        // Validate new password confirmation
        if (!newPassword.equals(confirmPassword)) {
            redirectAttributes.addFlashAttribute("error", "New passwords do not match");
            return "redirect:/profile";
        }

        // Validate password length
        if (newPassword.length() < 8) {
            redirectAttributes.addFlashAttribute("error", "Password must be at least 8 characters");
            return "redirect:/profile";
        }

        try {
            userService.updatePassword(Objects.requireNonNull(user.getId()), newPassword);
            redirectAttributes.addFlashAttribute("success", "Password updated successfully");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("error", e.getMessage());
        }

        return "redirect:/profile";
    }
}
