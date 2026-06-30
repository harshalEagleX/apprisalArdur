package com.shal;

import com.shal.common.entity.*;
import com.shal.common.repository.*;
import com.shal.user.service.ImpersonationService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Regression coverage for the impersonation audit gap fix.
 *
 * Before the fix: ImpersonationService.startImpersonation() and stopImpersonation()
 * made no audit log entry — the admin who initiated impersonation was invisible.
 *
 * After the fix:
 *  (1) startImpersonation() writes IMPERSONATION_STARTED to AuditLog
 *      → entry records both the admin's id and the target user's id
 *  (2) stopImpersonation() writes IMPERSONATION_ENDED
 *      → entry records the admin and the user they were impersonating
 *  (3) isImpersonating() transitions correctly through start → stop
 */
@SpringBootTest
class ImpersonationAuditIntegrationTests {

    @Autowired private ImpersonationService impersonationService;
    @Autowired private UserRepository userRepository;
    @Autowired private ClientRepository clientRepository;
    @Autowired private AuditLogRepository auditLogRepository;
    @Autowired private TransactionTemplate tx;

    @Test
    void startImpersonation_writesAuditLogEntry() {
        String tag = "IMPSTART_" + uuid();
        long[] ids = new long[2]; // adminId, targetId

        seed(tag, ids);
        try {
            // Authenticate as the admin in the security context
            setAdminContext(ids[0], tag + "_admin");

            boolean started = impersonationService.startImpersonation(ids[1]);
            assertThat(started).as("startImpersonation should succeed").isTrue();
            assertThat(impersonationService.isImpersonating()).isTrue();

            List<AuditLog> logs = tx.execute(s ->
                    auditLogRepository.findRecentByUserId(ids[0]));
            assertThat(logs)
                    .as("IMPERSONATION_STARTED audit entry must be written")
                    .anyMatch(l -> "IMPERSONATION_STARTED".equals(l.getAction())
                            && l.getEntityId() != null && l.getEntityId().equals(ids[1]));
        } finally {
            SecurityContextHolder.clearContext();
            cleanup(tag, ids);
        }
    }

    @Test
    void stopImpersonation_writesAuditLogEntry() {
        String tag = "IMPSTOP_" + uuid();
        long[] ids = new long[2];

        seed(tag, ids);
        try {
            setAdminContext(ids[0], tag + "_admin");

            impersonationService.startImpersonation(ids[1]);
            boolean stopped = impersonationService.stopImpersonation();

            assertThat(stopped).as("stopImpersonation should succeed").isTrue();
            assertThat(impersonationService.isImpersonating()).isFalse();

            List<AuditLog> logs = tx.execute(s ->
                    auditLogRepository.findRecentByUserId(ids[0]));
            assertThat(logs)
                    .as("IMPERSONATION_ENDED audit entry must be written")
                    .anyMatch(l -> "IMPERSONATION_ENDED".equals(l.getAction()));
        } finally {
            SecurityContextHolder.clearContext();
            cleanup(tag, ids);
        }
    }

    @Test
    void stopWithoutStart_returnsFalse() {
        SecurityContextHolder.clearContext();
        assertThat(impersonationService.stopImpersonation())
                .as("stopping when not impersonating must return false").isFalse();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void seed(String tag, long[] ids) {
        tx.executeWithoutResult(s -> {
            Client c = clientRepository.save(
                    Client.builder().name(tag).code(tag).status("ACTIVE").build());
            User admin = userRepository.save(User.builder()
                    .username(tag + "_admin").password("x").role(Role.ADMIN)
                    .fullName(tag + " Admin").build());
            User target = userRepository.save(User.builder()
                    .username(tag + "_target").password("x").role(Role.REVIEWER)
                    .fullName(tag + " Target").build());
            ids[0] = admin.getId(); ids[1] = target.getId();
        });
    }

    private void cleanup(String tag, long[] ids) {
        tx.executeWithoutResult(s -> {
            // Remove audit log entries for these users before deleting the users
            for (long uid : ids) {
                if (uid != 0) auditLogRepository.findRecentByUserId(uid).forEach(auditLogRepository::delete);
            }
            for (String name : List.of(tag + "_admin", tag + "_target")) {
                userRepository.findByUsername(name).ifPresent(userRepository::delete);
            }
            clientRepository.findAll().stream().filter(c -> tag.equals(c.getCode()))
                    .forEach(clientRepository::delete);
        });
    }

    private void setAdminContext(long userId, String username) {
        com.shal.common.security.UserPrincipal principal =
                new com.shal.common.security.UserPrincipal(
                        userRepository.findById(userId).orElseThrow());
        UsernamePasswordAuthenticationToken auth = new UsernamePasswordAuthenticationToken(
                principal, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
        org.springframework.security.core.context.SecurityContext ctx =
                SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(auth);
        SecurityContextHolder.setContext(ctx);
    }

    private static String uuid() {
        return UUID.randomUUID().toString().substring(0, 8).toUpperCase();
    }
}
