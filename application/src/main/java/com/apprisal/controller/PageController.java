package com.apprisal.controller;

import com.apprisal.entity.Role;
import com.apprisal.service.UserPrincipal;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/**
 * Controller for serving web pages and handling navigation.
 */
@Controller
public class PageController {

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/")
    public String home(@AuthenticationPrincipal UserPrincipal principal) {
        if (principal == null) {
            return "redirect:/login";
        }
        return redirectByRole(principal);
    }

    @GetMapping("/dashboard")
    public String dashboard(@AuthenticationPrincipal UserPrincipal principal) {
        return redirectByRole(principal);
    }

    private String redirectByRole(UserPrincipal principal) {
        Role role = principal.getUser().getRole();
        return switch (role) {
            case ADMIN -> "redirect:/admin/dashboard";
            case CLIENT -> "redirect:/client/dashboard";
            case REVIEWER -> "redirect:/reviewer/dashboard";
        };
    }
}
