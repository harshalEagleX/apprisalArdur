package com.apprisal.service;

import com.apprisal.entity.User;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

import java.util.Optional;
import java.util.Stack;
import java.util.Objects;
import org.springframework.lang.NonNull;

/**
 * Service for admin impersonation functionality.
 * Allows admins to impersonate other users for support/debugging.
 */
@Service
public class ImpersonationService {

    // Thread-local stack to track original authentication for nested impersonation
    private static final ThreadLocal<Stack<Authentication>> originalAuthStack = ThreadLocal.withInitial(Stack::new);

    private final UserService userService;

    public ImpersonationService(UserService userService) {
        this.userService = userService;
    }

    /**
     * Start impersonating a user. Only ADMIN can impersonate.
     * 
     * @param targetUserId The user ID to impersonate
     * @return true if impersonation started successfully
     */
    public boolean startImpersonation(@NonNull Long targetUserId) {
        Authentication currentAuth = SecurityContextHolder.getContext().getAuthentication();

        if (currentAuth == null || !hasAdminRole(currentAuth)) {
            return false;
        }

        Optional<User> targetUserOpt = userService.findById(targetUserId);
        if (targetUserOpt.isEmpty()) {
            return false;
        }

        User targetUser = Objects.requireNonNull(targetUserOpt.get());
        UserPrincipal targetPrincipal = new UserPrincipal(targetUser);

        // Save current authentication
        originalAuthStack.get().push(currentAuth);

        // Create new authentication for target user with special marker
        UsernamePasswordAuthenticationToken impersonatedAuth = new UsernamePasswordAuthenticationToken(
                targetPrincipal,
                null,
                targetPrincipal.getAuthorities());

        // Set the impersonated authentication
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(impersonatedAuth);
        SecurityContextHolder.setContext(context);

        return true;
    }

    /**
     * Stop impersonation and restore original authentication.
     * 
     * @return true if impersonation stopped successfully
     */
    public boolean stopImpersonation() {
        Stack<Authentication> stack = originalAuthStack.get();

        if (stack.isEmpty()) {
            return false;
        }

        Authentication originalAuth = stack.pop();

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(originalAuth);
        SecurityContextHolder.setContext(context);

        if (stack.isEmpty()) {
            originalAuthStack.remove();
        }

        return true;
    }

    /**
     * Check if currently impersonating.
     */
    public boolean isImpersonating() {
        return !originalAuthStack.get().isEmpty();
    }

    /**
     * Get the original admin user if currently impersonating.
     */
    public Optional<User> getOriginalUser() {
        Stack<Authentication> stack = originalAuthStack.get();

        if (stack.isEmpty()) {
            return Optional.empty();
        }

        Authentication originalAuth = stack.peek();
        if (originalAuth.getPrincipal() instanceof UserPrincipal) {
            return Optional.of(((UserPrincipal) originalAuth.getPrincipal()).getUser());
        }

        return Optional.empty();
    }

    private boolean hasAdminRole(Authentication auth) {
        return auth.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN"));
    }
}
