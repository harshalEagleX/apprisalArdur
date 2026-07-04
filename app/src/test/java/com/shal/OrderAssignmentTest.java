package com.shal;

import com.shal.batch.controller.api.OrderApiController;
import com.shal.common.entity.*;
import com.shal.common.repository.*;
import com.shal.common.security.UserPrincipal;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Order-level reviewer assignment: manual (single + bulk), auto-assign balancing, and
 * the reviewer's own order queue. Assignment is per-Order — a 50-order batch is never
 * dumped on one reviewer.
 */
@SpringBootTest
class OrderAssignmentTest {

    @Autowired private OrderApiController orderApiController;
    @Autowired private ClientRepository clientRepository;
    @Autowired private UserRepository userRepository;
    @Autowired private AppraisalTransactionRepository orderRepository;
    @Autowired private TransactionTemplate tx;

    private long clientId;
    private long adminId;
    private final List<Long> orderIds = new ArrayList<>();
    private final List<Long> reviewerIds = new ArrayList<>();
    private String tag;

    @BeforeEach
    void authenticateAsAdmin() {
        // @PreAuthorize("hasRole('ADMIN')") on the controller requires an Authentication
        // in the context even when the method is invoked directly (AOP proxy still runs).
        org.springframework.security.core.context.SecurityContextHolder.getContext().setAuthentication(
                new org.springframework.security.authentication.UsernamePasswordAuthenticationToken(
                        "admin", "x",
                        List.of(new org.springframework.security.core.authority.SimpleGrantedAuthority("ROLE_ADMIN"))));
    }

    @BeforeEach
    void seed() {
        tag = "ASG_" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        tx.executeWithoutResult(s -> {
            Client c = clientRepository.save(Client.builder().name(tag).code(tag).status("ACTIVE").build());
            clientId = c.getId();
            // Client-scoped admin + reviewers so auto-assign is isolated to this client.
            User admin = User.builder()
                    .username(tag + "_admin").password("x").role(Role.ADMIN).fullName(tag).build();
            admin.setClient(c);
            adminId = userRepository.save(admin).getId();
            for (int i = 0; i < 3; i++) {
                User rev = User.builder()
                        .username(tag + "_rev" + i).password("x").role(Role.REVIEWER).fullName("Rev" + i).build();
                rev.setClient(c);
                reviewerIds.add(userRepository.save(rev).getId());
            }
            for (int i = 0; i < 6; i++) {
                AppraisalTransaction o = new AppraisalTransaction();
                o.setTransactionRef(tag + "-O" + i);
                o.setClient(c);
                o.setStatus(TransactionStatus.RECEIVED);
                o.setDocumentStatus(OrderDocumentStatus.NEEDS_REVIEW);
                orderIds.add(orderRepository.save(o).getId());
            }
        });
    }

    @AfterEach
    void cleanup() {
        org.springframework.security.core.context.SecurityContextHolder.clearContext();
        // Only orders are removed. The admin/reviewer users are referenced by
        // business_event (audit) rows the assignment wrote, so — like the other intake
        // tests — the tagged user/client rows are left behind as harmless test data.
        tx.executeWithoutResult(s ->
                orderIds.forEach(id -> orderRepository.findById(id).ifPresent(orderRepository::delete)));
    }

    private UserPrincipal admin() {
        // Super-admin (no client scope) so it can act on the seeded client's orders.
        return new UserPrincipal(userRepository.findById(adminId).orElseThrow());
    }

    @Test
    void manualAssign_setsReviewerOnOrder() {
        Long orderId = orderIds.get(0);
        Long reviewerId = reviewerIds.get(0);

        ResponseEntity<?> resp = tx.execute(s ->
                orderApiController.assignReviewer(orderId, Map.of("reviewerId", reviewerId), admin()));
        assertThat(resp.getStatusCode().is2xxSuccessful()).isTrue();

        Long assigned = tx.execute(s -> orderRepository.findById(orderId).orElseThrow()
                .getAssignedReviewer() != null
                ? orderRepository.findById(orderId).orElseThrow().getAssignedReviewer().getId() : null);
        assertThat(assigned).isEqualTo(reviewerId);
    }

    @Test
    void assigningNonReviewer_isRejected() {
        ResponseEntity<?> resp = tx.execute(s ->
                orderApiController.assignReviewer(orderIds.get(0), Map.of("reviewerId", adminId), admin()));
        assertThat(resp.getStatusCode().value()).isEqualTo(400);
    }

    @Test
    void bulkAssign_setsReviewerOnAllSelected() {
        List<Long> selected = orderIds.subList(0, 4);
        Long reviewerId = reviewerIds.get(1);

        tx.executeWithoutResult(s -> orderApiController.assignReviewerBulk(
                Map.of("orderIds", selected, "reviewerId", reviewerId), admin()));

        long count = tx.execute(s -> selected.stream()
                .map(id -> orderRepository.findById(id).orElseThrow())
                .filter(o -> o.getAssignedReviewer() != null && reviewerId.equals(o.getAssignedReviewer().getId()))
                .count());
        assertThat(count).isEqualTo(4);
    }

    @Test
    void autoAssign_distributesUnassignedAcrossReviewers() {
        tx.executeWithoutResult(s -> orderApiController.autoAssign(Map.of(), admin()));

        // All 6 orders assigned, spread across the 3 reviewers (balanced → 2 each).
        Map<Long, Long> perReviewer = tx.execute(s -> {
            Map<Long, Long> m = new java.util.HashMap<>();
            for (Long id : orderIds) {
                AppraisalTransaction o = orderRepository.findById(id).orElseThrow();
                assertThat(o.getAssignedReviewer()).as("order " + id + " must be assigned").isNotNull();
                m.merge(o.getAssignedReviewer().getId(), 1L, Long::sum);
            }
            return m;
        });
        assertThat(perReviewer.keySet()).containsExactlyInAnyOrderElementsOf(reviewerIds);
        assertThat(perReviewer.values()).allSatisfy(v -> assertThat(v).isEqualTo(2L));
    }

    @Test
    void assignBeforeQcDone_isBlocked() {
        Long orderId = orderIds.get(0);
        // Move it to a pre-QC state — assignment must be refused until QC is done.
        tx.executeWithoutResult(s -> {
            AppraisalTransaction o = orderRepository.findById(orderId).orElseThrow();
            o.setDocumentStatus(OrderDocumentStatus.READY_FOR_QC);
            orderRepository.save(o);
        });

        ResponseEntity<?> resp = tx.execute(s ->
                orderApiController.assignReviewer(orderId, Map.of("reviewerId", reviewerIds.get(0)), admin()));

        assertThat(resp.getStatusCode().value()).isEqualTo(400);
        Long assigned = tx.execute(s -> {
            AppraisalTransaction o = orderRepository.findById(orderId).orElseThrow();
            return o.getAssignedReviewer() != null ? o.getAssignedReviewer().getId() : null;
        });
        assertThat(assigned).as("pre-QC order must not get a reviewer").isNull();
    }

    @Test
    void autoAssign_skipsOrdersWithoutCompletedQc() {
        Long preQc = orderIds.get(0);
        tx.executeWithoutResult(s -> {
            AppraisalTransaction o = orderRepository.findById(preQc).orElseThrow();
            o.setDocumentStatus(OrderDocumentStatus.INCOMPLETE);
            orderRepository.save(o);
        });

        tx.executeWithoutResult(s -> orderApiController.autoAssign(Map.of(), admin()));

        Long assigned = tx.execute(s -> {
            AppraisalTransaction o = orderRepository.findById(preQc).orElseThrow();
            return o.getAssignedReviewer() != null ? o.getAssignedReviewer().getId() : null;
        });
        assertThat(assigned).as("pre-QC order must not be auto-assigned").isNull();
    }

    @Test
    void reviewerQueue_returnsOnlyOwnOrders() {
        Long reviewerId = reviewerIds.get(2);
        tx.executeWithoutResult(s -> orderApiController.assignReviewerBulk(
                Map.of("orderIds", orderIds.subList(0, 2), "reviewerId", reviewerId), admin()));

        long queued = tx.execute(s -> orderRepository.findByAssignedReviewer(
                reviewerId, null, org.springframework.data.domain.PageRequest.of(0, 20)).getTotalElements());
        assertThat(queued).isEqualTo(2);
    }
}
