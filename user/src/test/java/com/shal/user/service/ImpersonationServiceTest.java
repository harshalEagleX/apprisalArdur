package com.shal.user.service;

import com.shal.common.entity.Role;
import com.shal.common.entity.User;
import com.shal.common.security.UserPrincipal;
import com.shal.common.service.AuditLogService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * Admin impersonation — a privilege-escalation surface if it goes wrong.
 *
 * The two properties that must hold:
 *   1. ONLY an admin can start it. A non-admin who could impersonate would be a
 *      straight privilege escalation.
 *   2. It is ALWAYS audited with BOTH identities. Actions taken while impersonating
 *      are recorded under the target user, so without this separate event there is
 *      no record of which admin chose to become them — the accountability gap the
 *      code comments call out.
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class ImpersonationServiceTest {

    @Mock UserService userService;
    @Mock AuditLogService auditLogService;

    private ImpersonationService svc() {
        return new ImpersonationService(userService, auditLogService);
    }

    private static User user(long id, String name, Role role) {
        User u = User.builder().username(name).password("x").role(role).build();
        u.setId(id);
        return u;
    }

    private static void authenticateAs(User u) {
        UserPrincipal p = new UserPrincipal(u);
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(p, null, p.getAuthorities()));
    }

    private static String currentUsername() {
        Authentication a = SecurityContextHolder.getContext().getAuthentication();
        return a == null ? null : ((UserPrincipal) a.getPrincipal()).getUser().getUsername();
    }

    @AfterEach
    void tearDown() {
        // stop any impersonation left on this thread, then clear
        try { svc().stopImpersonation(); } catch (Exception ignored) { }
        SecurityContextHolder.clearContext();
    }

    // ── authorization ───────────────────────────────────────────────────────

    @Test
    @DisplayName("a REVIEWER cannot impersonate — that would be privilege escalation")
    void reviewerCannotImpersonate() {
        authenticateAs(user(1L, "reviewer", Role.REVIEWER));
        assertThat(svc().startImpersonation(2L)).isFalse();
        assertThat(currentUsername()).isEqualTo("reviewer");   // context untouched
        verifyNoInteractions(auditLogService);
    }

    @Test
    @DisplayName("an unauthenticated caller cannot impersonate")
    void anonymousCannotImpersonate() {
        SecurityContextHolder.clearContext();
        assertThat(svc().startImpersonation(2L)).isFalse();
        verifyNoInteractions(userService, auditLogService);
    }

    @Test
    @DisplayName("impersonating a user who does not exist fails and changes nothing")
    void unknownTargetFails() {
        authenticateAs(user(1L, "admin", Role.ADMIN));
        when(userService.findById(99L)).thenReturn(Optional.empty());
        assertThat(svc().startImpersonation(99L)).isFalse();
        assertThat(currentUsername()).isEqualTo("admin");
        verifyNoInteractions(auditLogService);
    }

    // ── the happy path ──────────────────────────────────────────────────────

    @Test
    @DisplayName("an ADMIN can impersonate, and the security context becomes the target")
    void adminCanImpersonate() {
        authenticateAs(user(1L, "admin", Role.ADMIN));
        when(userService.findById(2L)).thenReturn(Optional.of(user(2L, "target", Role.REVIEWER)));

        assertThat(svc().startImpersonation(2L)).isTrue();
        assertThat(currentUsername()).isEqualTo("target");
    }

    @Test
    @DisplayName("starting impersonation is audited with BOTH the admin and the target")
    void impersonationIsAudited() {
        // Without both identities in one record there is no way to answer
        // "which admin acted as this user?" after the fact.
        authenticateAs(user(1L, "admin", Role.ADMIN));
        when(userService.findById(2L)).thenReturn(Optional.of(user(2L, "target", Role.REVIEWER)));

        svc().startImpersonation(2L);

        verify(auditLogService).log(any(), eq("IMPERSONATION_STARTED"), eq("User"), eq(2L),
                argThat(d -> d.contains("admin=admin") && d.contains("target=target")
                          && d.contains("admin_id=1") && d.contains("target_id=2")),
                any(), any());
    }

    // ── restore ─────────────────────────────────────────────────────────────

    @Test
    @DisplayName("stopping restores the original admin identity")
    void stopRestoresOriginal() {
        ImpersonationService svc = svc();
        authenticateAs(user(1L, "admin", Role.ADMIN));
        when(userService.findById(2L)).thenReturn(Optional.of(user(2L, "target", Role.REVIEWER)));

        svc.startImpersonation(2L);
        assertThat(currentUsername()).isEqualTo("target");

        assertThat(svc.stopImpersonation()).isTrue();
        assertThat(currentUsername()).isEqualTo("admin");
    }

    @Test
    @DisplayName("stopping when not impersonating is a no-op, not an error")
    void stopWithoutStartIsFalse() {
        authenticateAs(user(1L, "admin", Role.ADMIN));
        assertThat(svc().stopImpersonation()).isFalse();
        assertThat(currentUsername()).isEqualTo("admin");
    }

    @Test
    @DisplayName("isImpersonating reflects the current state in both directions")
    void isImpersonatingReflectsState() {
        ImpersonationService svc = svc();
        authenticateAs(user(1L, "admin", Role.ADMIN));
        when(userService.findById(2L)).thenReturn(Optional.of(user(2L, "target", Role.REVIEWER)));

        assertThat(svc.isImpersonating()).isFalse();
        svc.startImpersonation(2L);
        assertThat(svc.isImpersonating()).isTrue();
        svc.stopImpersonation();
        assertThat(svc.isImpersonating()).isFalse();
    }

    @Test
    @DisplayName("getOriginalUser names the admin behind the impersonation")
    void originalUserIsTheAdmin() {
        ImpersonationService svc = svc();
        authenticateAs(user(1L, "admin", Role.ADMIN));
        when(userService.findById(2L)).thenReturn(Optional.of(user(2L, "target", Role.REVIEWER)));

        assertThat(svc.getOriginalUser()).isEmpty();
        svc.startImpersonation(2L);
        assertThat(svc.getOriginalUser()).map(User::getUsername).contains("admin");
    }
}
