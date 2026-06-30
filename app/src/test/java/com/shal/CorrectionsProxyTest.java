package com.shal;

import com.shal.common.entity.*;
import com.shal.common.repository.*;
import com.shal.common.security.UserPrincipal;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.context.WebApplicationContext;

import java.time.LocalDateTime;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Regression coverage for VF-6 (corrections bypass).
 *
 * The /api/reviewer/corrections endpoint must enforce QC result ownership
 * for REVIEWERs before proxying to Python. Scenarios:
 *
 *  (1) Unauthenticated → 401/403 (blocked by Spring Security before reaching controller)
 *  (2) REVIEWER not assigned to the batch that owns the QC result → 403
 *  (3) REVIEWER assigned to the batch → 200 (proxied; Python stubbed)
 *  (4) ADMIN → 200 regardless of assignment (no ownership check for admins)
 */
@SpringBootTest
class CorrectionsProxyTest {

    @Autowired private WebApplicationContext context;
    @MockitoBean private com.shal.qc.service.PythonClientService pythonClientService;

    @Autowired private ClientRepository clientRepository;
    @Autowired private UserRepository userRepository;
    @Autowired private BatchRepository batchRepository;
    @Autowired private BatchFileRepository batchFileRepository;
    @Autowired private QCResultRepository qcResultRepository;
    @Autowired private AuditLogRepository auditLogRepository;
    @Autowired private TransactionTemplate tx;

    private MockMvc mvc;

    private long assignedReviewerId;
    private long unassignedReviewerId;
    private long adminId;
    private long batchId;
    private long qcResultId;
    private String tag;

    @BeforeEach
    void seed() {
        mvc = MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build();

        tag = "CPT_" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        long[] ids = new long[5]; // [clientId, assignedId, unassignedId, adminId, batchId]

        tx.executeWithoutResult(s -> {
            Client c = clientRepository.save(
                    Client.builder().name(tag).code(tag).status("ACTIVE").build());
            ids[0] = c.getId();

            User assigned = userRepository.save(User.builder()
                    .username(tag + "_assigned").password("x")
                    .role(Role.REVIEWER).fullName(tag + " Assigned").build());
            ids[1] = assigned.getId();

            User unassigned = userRepository.save(User.builder()
                    .username(tag + "_unassigned").password("x")
                    .role(Role.REVIEWER).fullName(tag + " Unassigned").build());
            ids[2] = unassigned.getId();

            User admin = userRepository.save(User.builder()
                    .username(tag + "_admin").password("x")
                    .role(Role.ADMIN).fullName(tag + " Admin").build());
            ids[3] = admin.getId();

            Batch b = batchRepository.save(Batch.builder()
                    .parentBatchId(tag).client(c)
                    .status(BatchStatus.IN_REVIEW)
                    .assignedReviewer(assigned)
                    .createdBy(admin).build());
            ids[4] = b.getId();

            BatchFile f = batchFileRepository.save(BatchFile.builder()
                    .batch(b).fileType(FileType.APPRAISAL).filename(tag + ".pdf")
                    .storagePath("/test/" + tag + "/appraisal.pdf")
                    .status(FileStatus.COMPLETED).build());

            QCResult r = QCResult.builder()
                    .batchFile(f).qcDecision(QCDecision.TO_VERIFY)
                    .totalRules(2).build();
            r.setProcessedAt(LocalDateTime.now());
            r = qcResultRepository.save(r);
            qcResultId = r.getId();
        });

        assignedReviewerId   = ids[1];
        unassignedReviewerId = ids[2];
        adminId              = ids[3];
        batchId              = ids[4];

        when(pythonClientService.submitCorrection(any())).thenReturn("{\"ok\":true}");
    }

    @AfterEach
    void cleanup() {
        tx.executeWithoutResult(s -> {
            qcResultRepository.findById(qcResultId).ifPresent(qcResultRepository::delete);
            batchFileRepository.findByBatchId(batchId).forEach(batchFileRepository::delete);
            batchRepository.findById(batchId).ifPresent(batchRepository::delete);
            // Delete audit log entries before users (FK: audit_log.user_id → _user.id)
            for (String name : new String[]{tag + "_assigned", tag + "_unassigned", tag + "_admin"}) {
                userRepository.findByUsername(name).ifPresent(u -> {
                    auditLogRepository.findRecentByUserId(u.getId()).forEach(auditLogRepository::delete);
                    userRepository.delete(u);
                });
            }
            clientRepository.findAll().stream()
                    .filter(c -> tag.equals(c.getCode()))
                    .forEach(clientRepository::delete);
        });
    }

    // ── (1) Unauthenticated ───────────────────────────────────────────────────

    @Test
    void unauthenticated_blockedBySecurityFilter() throws Exception {
        int statusCode = mvc.perform(post("/api/reviewer/corrections")
                        .with(anonymous())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body(qcResultId)))
                .andReturn().getResponse().getStatus();
        assertThat(statusCode).as("unauthenticated request must be blocked").isIn(401, 403);
    }

    // ── (2) REVIEWER not assigned to the QC result's batch → 403 ────────────

    @Test
    void unassignedReviewer_gets403() throws Exception {
        User u = tx.execute(s -> userRepository.findById(unassignedReviewerId).orElseThrow());
        mvc.perform(post("/api/reviewer/corrections")
                        .with(user(new UserPrincipal(u)))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body(qcResultId)))
                .andExpect(status().isForbidden());
    }

    // ── (3) REVIEWER assigned to the batch → 200 ─────────────────────────────

    @Test
    void assignedReviewer_gets200() throws Exception {
        User u = tx.execute(s -> userRepository.findById(assignedReviewerId).orElseThrow());
        mvc.perform(post("/api/reviewer/corrections")
                        .with(user(new UserPrincipal(u)))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body(qcResultId)))
                .andExpect(status().isOk());
    }

    // ── (4) ADMIN bypasses ownership check → 200 ─────────────────────────────

    @Test
    void admin_bypassesOwnershipCheck_gets200() throws Exception {
        User u = tx.execute(s -> userRepository.findById(adminId).orElseThrow());
        mvc.perform(post("/api/reviewer/corrections")
                        .with(user(new UserPrincipal(u)))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body(qcResultId)))
                .andExpect(status().isOk());
    }

    private static String body(long qcResultId) {
        return "{\"qc_result_id\": " + qcResultId + ", \"document_id\": \"doc-test-001\"}";
    }
}
