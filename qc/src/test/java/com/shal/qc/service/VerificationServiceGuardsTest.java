package com.shal.qc.service;

import com.shal.common.entity.BatchFile;
import com.shal.common.entity.QCResult;
import com.shal.common.entity.QCRuleResult;
import com.shal.common.entity.User;
import com.shal.common.repository.*;
import com.shal.common.service.AuditLogService;
import com.shal.common.service.BusinessEventService;
import com.shal.common.service.OrderStatusService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * The guards around saving a reviewer decision.
 *
 * VerificationService was at 0% coverage while owning the rules that stop two
 * reviewers colliding, stop writes landing on a superseded QC run, and stop a
 * reviewer clicking through findings faster than they can have read them. Each
 * of these throws with a message the reviewer sees, so both the CONDITION and
 * the WORDING are behaviour worth pinning.
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class VerificationServiceGuardsTest {

    @Mock QCResultRepository qcResultRepository;
    @Mock QCRuleResultRepository qcRuleResultRepository;
    @Mock BatchRepository batchRepository;
    @Mock ProcessingMetricsRepository processingMetricsRepository;
    @Mock OperatorSessionRepository operatorSessionRepository;
    @Mock AuditLogService auditLogService;
    @Mock BusinessEventService businessEventService;
    @Mock PythonClientService pythonClientService;
    @Mock OrderStatusService orderStatusService;

    private VerificationService svc;

    private static final String TOKEN = "session-abc";

    @BeforeEach
    void setUp() {
        svc = new VerificationService(qcResultRepository, qcRuleResultRepository, batchRepository,
                processingMetricsRepository, operatorSessionRepository, auditLogService,
                businessEventService, pythonClientService, orderStatusService);
    }

    private static User user(long id, String name) {
        User u = new User();
        u.setId(id);
        u.setUsername(name);
        u.setFullName(name);
        return u;
    }

    /** A QCResult with a live session owned by TOKEN. */
    private static QCResult liveResult() {
        QCResult r = new QCResult();
        r.setId(1L);
        r.setReviewSessionToken(TOKEN);
        r.setReviewLockExpiresAt(LocalDateTime.now().plusMinutes(30));
        return r;
    }

    private static QCRuleResult ruleOn(QCResult parent, String status) {
        QCRuleResult rr = new QCRuleResult();
        rr.setId(10L);
        rr.setRuleId("S-1");
        rr.setStatus(status);
        rr.setQcResult(parent);
        return rr;
    }

    private void givenRule(QCRuleResult rr) {
        when(qcRuleResultRepository.findByIdForUpdate(rr.getId())).thenReturn(Optional.of(rr));
        // List.of(Object[]) infers List<Object> — build the List<Object[]> explicitly.
        List<Object[]> progress = new java.util.ArrayList<>();
        progress.add(new Object[]{0L, 0L, 0L});
        when(qcRuleResultRepository.progressCountsForQcResult(any())).thenReturn(progress);
    }

    private QCRuleResult save(QCRuleResult rr, String decision, String token,
                              Long latencyMs, Boolean acknowledged) {
        return svc.saveDecision(rr.getId(), decision, "ok", token, latencyMs, acknowledged,
                user(2L, "reviewer"), "127.0.0.1", "junit");
    }

    // ── session ownership ───────────────────────────────────────────────────

    @Test
    @DisplayName("a decision with no session token is refused")
    void blankSessionTokenRefused() {
        QCRuleResult rr = ruleOn(liveResult(), "pass");
        givenRule(rr);
        assertThatThrownBy(() -> save(rr, "PASS", "  ", 9_000L, true))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("session token is required");
    }

    @Test
    @DisplayName("a decision from a STALE session is refused, not silently applied")
    void staleSessionRefused() {
        // Two tabs open: the older one must not overwrite the newer session's work.
        QCRuleResult rr = ruleOn(liveResult(), "pass");
        givenRule(rr);
        assertThatThrownBy(() -> save(rr, "PASS", "some-other-token", 9_000L, true))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("stale");
    }

    @Test
    @DisplayName("a decision on an EXPIRED lock is refused")
    void expiredLockRefused() {
        QCResult qc = liveResult();
        qc.setReviewLockExpiresAt(LocalDateTime.now().minusMinutes(1));
        QCRuleResult rr = ruleOn(qc, "pass");
        givenRule(rr);
        assertThatThrownBy(() -> save(rr, "PASS", TOKEN, 9_000L, true))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("timed out");
    }

    // ── document currency ───────────────────────────────────────────────────

    @Test
    @DisplayName("writes to a SUPERSEDED QC run are blocked, since they would be lost")
    void supersededResultBlocked() {
        QCResult qc = liveResult();
        qc.setBatchFile(new BatchFile());
        qc.setSupersededAt(LocalDateTime.now().minusMinutes(5));
        QCRuleResult rr = ruleOn(qc, "pass");
        givenRule(rr);
        assertThatThrownBy(() -> save(rr, "PASS", TOKEN, 9_000L, true))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("no longer the current");
    }

    @Test
    @DisplayName("a re-uploaded document (hash changed) blocks decisions")
    void changedDocumentHashBlocked() {
        QCResult qc = liveResult();
        BatchFile bf = new BatchFile();
        bf.setContentHash("NEW-HASH");
        qc.setBatchFile(bf);
        qc.setSourceDocumentHash("OLD-HASH");
        QCRuleResult rr = ruleOn(qc, "pass");
        givenRule(rr);
        assertThatThrownBy(() -> save(rr, "PASS", TOKEN, 9_000L, true))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("newer version");
    }

    @Test
    @DisplayName("a newer document VERSION blocks decisions")
    void newerDocumentVersionBlocked() {
        QCResult qc = liveResult();
        BatchFile bf = new BatchFile();
        bf.setContentVersion(3L);
        qc.setBatchFile(bf);
        qc.setSourceDocumentVersion(2L);
        QCRuleResult rr = ruleOn(qc, "pass");
        givenRule(rr);
        assertThatThrownBy(() -> save(rr, "PASS", TOKEN, 9_000L, true))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("newer version");
    }

    @Test
    @DisplayName("an OLDER version does not block — only a newer one supersedes")
    void olderVersionDoesNotBlock() {
        QCResult qc = liveResult();
        BatchFile bf = new BatchFile();
        bf.setContentVersion(1L);
        qc.setBatchFile(bf);
        qc.setSourceDocumentVersion(2L);
        QCRuleResult rr = ruleOn(qc, "pass");
        givenRule(rr);
        assertThat(save(rr, "PASS", TOKEN, 9_000L, true)).isNotNull();
    }

    // ── the decision word itself ────────────────────────────────────────────

    @Test
    @DisplayName("PASS applies MANUAL_PASS; FAIL applies FAIL")
    void decisionMapsToStatus() {
        QCRuleResult pass = ruleOn(liveResult(), "verify");
        pass.setFirstPresentedAt(LocalDateTime.now().minusMinutes(1));
        givenRule(pass);
        assertThat(save(pass, "PASS", TOKEN, 9_000L, true).getStatus()).isEqualTo("MANUAL_PASS");

        QCRuleResult fail = ruleOn(liveResult(), "verify");
        fail.setId(11L);
        fail.setFirstPresentedAt(LocalDateTime.now().minusMinutes(1));
        givenRule(fail);
        assertThat(save(fail, "FAIL", TOKEN, 9_000L, true).getStatus()).isEqualTo("FAIL");
    }

    @Test
    @DisplayName("the decision word is case- and space-insensitive")
    void decisionIsNormalized() {
        QCRuleResult rr = ruleOn(liveResult(), "pass");
        givenRule(rr);
        assertThat(save(rr, "  pass  ", TOKEN, 9_000L, true).getStatus()).isEqualTo("MANUAL_PASS");
    }

    @Test
    @DisplayName("any word other than PASS/FAIL is rejected rather than guessed at")
    void unknownDecisionRejected() {
        QCRuleResult rr = ruleOn(liveResult(), "pass");
        givenRule(rr);
        assertThatThrownBy(() -> save(rr, "MAYBE", TOKEN, 9_000L, true))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("PASS or FAIL");
    }

    // ── engagement guards (VERIFY items only) ───────────────────────────────

    @Test
    @DisplayName("a VERIFY item decided faster than a human could read it is refused")
    void tooFastOnVerifyRefused() {
        QCRuleResult rr = ruleOn(liveResult(), "verify");
        rr.setFirstPresentedAt(LocalDateTime.now());   // just presented
        givenRule(rr);
        assertThatThrownBy(() -> save(rr, "PASS", TOKEN, 10L, true))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("review the referenced sections");
    }

    @Test
    @DisplayName("the SERVER's elapsed time counts, so a faked client latency cannot bypass the guard")
    void serverLatencyWins() {
        // Client claims 0ms but the item has genuinely been on screen a while —
        // max(client, server) means the guard passes on real elapsed time.
        QCRuleResult rr = ruleOn(liveResult(), "verify");
        rr.setFirstPresentedAt(LocalDateTime.now().minusMinutes(2));
        givenRule(rr);
        assertThat(save(rr, "PASS", TOKEN, 0L, true)).isNotNull();
    }

    @Test
    @DisplayName("a BLOCKING verify item requires explicit acknowledgement")
    void blockingRequiresAcknowledgement() {
        QCRuleResult rr = ruleOn(liveResult(), "verify");
        rr.setSeverity("BLOCKING");
        rr.setFirstPresentedAt(LocalDateTime.now().minusMinutes(1));
        givenRule(rr);
        assertThatThrownBy(() -> save(rr, "PASS", TOKEN, 9_000L, false))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("acknowledgement");
        // ...and succeeds once acknowledged
        assertThat(save(rr, "PASS", TOKEN, 9_000L, true)).isNotNull();
    }

    @Test
    @DisplayName("a settled (non-verify) item is not subject to the engagement guards")
    void settledItemsSkipEngagementGuards() {
        QCRuleResult rr = ruleOn(liveResult(), "pass");
        givenRule(rr);
        assertThat(save(rr, "PASS", TOKEN, 0L, null)).isNotNull();
    }

    // ── cross-session and duplicate protection ──────────────────────────────

    @Test
    @DisplayName("an item already decided in ANOTHER session cannot be silently overwritten")
    void alreadyDecidedElsewhereRefused() {
        QCRuleResult rr = ruleOn(liveResult(), "verify");
        rr.setReviewerVerified(Boolean.TRUE);
        rr.setReviewSessionToken("a-different-session");
        rr.setFirstPresentedAt(LocalDateTime.now().minusMinutes(1));
        givenRule(rr);
        assertThatThrownBy(() -> save(rr, "FAIL", TOKEN, 9_000L, true))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("already decided in another session");
    }

    @Test
    @DisplayName("re-submitting the SAME decision is idempotent, not an error")
    void duplicateSubmissionIsIdempotent() {
        // A double-click or a retried request must not throw at the reviewer.
        QCRuleResult rr = ruleOn(liveResult(), "MANUAL_PASS");
        rr.setReviewSessionToken(TOKEN);
        rr.setReviewerVerified(Boolean.TRUE);
        rr.setReviewerComment("ok");
        givenRule(rr);
        assertThat(save(rr, "PASS", TOKEN, 9_000L, true)).isSameAs(rr);
        // short-circuited before any write
        verify(qcRuleResultRepository, never()).saveAndFlush(any());
    }

    // ── prior-decision count ────────────────────────────────────────────────

    @Test
    @DisplayName("priorActionCount counts only items a reviewer actually decided")
    void priorActionCountCountsDecidedOnly() {
        QCRuleResult decided = new QCRuleResult();
        decided.setReviewerVerified(Boolean.TRUE);
        QCRuleResult undecided = new QCRuleResult();
        when(qcRuleResultRepository.findVerificationItemsForQcResult(1L))
                .thenReturn(List.of(decided, undecided, new QCRuleResult()));
        assertThat(svc.priorActionCount(1L)).isEqualTo(1);
    }
}
