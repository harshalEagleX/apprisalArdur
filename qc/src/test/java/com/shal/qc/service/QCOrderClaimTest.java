package com.shal.qc.service;

import tools.jackson.databind.ObjectMapper;
import com.shal.common.cluster.ClusterCoordinator;
import com.shal.common.entity.AppraisalTransaction;
import com.shal.common.repository.AppraisalTransactionRepository;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.repository.BatchRepository;
import com.shal.common.repository.ClientRepository;
import com.shal.common.repository.LLMInteractionRepository;
import com.shal.common.repository.QCResultRepository;
import com.shal.common.repository.QCRuleResultRepository;
import com.shal.common.service.BusinessEventService;
import com.shal.common.service.FileMatchingService;
import com.shal.common.service.LinkageGateService;
import com.shal.common.service.OrderStatusService;
import com.shal.common.realtime.RealtimeEventPublisher;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.when;

/**
 * The Order QC claim — specifically, what happens when the claim FAILS.
 *
 * Regression cover for the 2026-07-19 incident: a Run QC click blocked inside the
 * claim transaction, and because the in-memory {@code activeOrders} set had already
 * been added to, every retry afterwards was refused with "another worker is active"
 * while the order row still read READY_FOR_QC. Nothing but a JVM restart cleared it.
 *
 * The invariant these tests pin: a failed claim NEVER leaves the order unrunnable.
 * The database row is the authority; the in-memory set must not outlive it.
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class QCOrderClaimTest {

    @Mock PythonClientService pythonClient;
    @Mock FileMatchingService fileMatchingService;
    @Mock QCResultRepository qcResultRepository;
    @Mock QCRuleResultRepository qcRuleResultRepository;
    @Mock LLMInteractionRepository llmInteractionRepository;
    @Mock ClientRepository clientRepository;
    @Mock BatchRepository batchRepository;
    @Mock BatchFileRepository batchFileRepository;
    @Mock RealtimeEventPublisher realtimeEventPublisher;
    @Mock BusinessEventService businessEventService;
    @Mock ClusterCoordinator clusterCoordinator;
    @Mock OrderStatusService orderStatusService;
    @Mock AppraisalTransactionRepository appraisalTransactionRepository;
    @Mock com.shal.common.repository.DocStatRepository docStatRepository;
    @Mock LinkageGateService linkageGateService;

    private QCProcessingService svc;

    private static final Long ORDER_ID = 1L;

    @BeforeEach
    void setUp() {
        svc = new QCProcessingService(
                pythonClient, fileMatchingService, qcResultRepository, qcRuleResultRepository,
                llmInteractionRepository, clientRepository, batchRepository, batchFileRepository,
                new ObjectMapper(), realtimeEventPublisher, businessEventService, clusterCoordinator,
                orderStatusService, appraisalTransactionRepository, docStatRepository, linkageGateService);

        // The entity is a stand-in only: OrderStatusService.markProcessing is the thing
        // being stubbed, and it is what actually claims the row.
        when(appraisalTransactionRepository.findById(ORDER_ID))
                .thenReturn(Optional.of(org.mockito.Mockito.mock(AppraisalTransaction.class)));
    }

    @Test
    @DisplayName("a claim that throws leaves the order runnable — the local claim is released")
    void claimThatThrows_doesNotStrandTheOrder() {
        when(orderStatusService.markProcessing(any())).thenReturn(true);
        // The exact failure seen in production: the business-event write blew up inside
        // the claim, after the in-memory set had been touched.
        doThrow(new IllegalStateException("Could not open JPA EntityManager for transaction"))
                .when(businessEventService).record(any(), any(), any(), any(), any(), any(),
                        any(), any(), any(), any(), any());

        assertThatThrownBy(() -> svc.claimOrderForProcessing(ORDER_ID, null))
                .isInstanceOf(IllegalStateException.class);

        // The whole point: the order is NOT stuck. Before the fix this returned false
        // forever ("another worker is active") until the JVM restarted.
        assertThat(svc.isOrderActive(ORDER_ID))
                .as("failed claim must not leave a phantom worker holding the order")
                .isFalse();
    }

    @Test
    @DisplayName("after a failed claim the very next attempt succeeds")
    void retryAfterFailedClaim_succeeds() {
        when(orderStatusService.markProcessing(any())).thenReturn(true);
        doThrow(new IllegalStateException("connection closed"))
                .when(businessEventService).record(any(), any(), any(), any(), any(), any(),
                        any(), any(), any(), any(), any());
        assertThatThrownBy(() -> svc.claimOrderForProcessing(ORDER_ID, null))
                .isInstanceOf(IllegalStateException.class);

        // Second attempt, with the transient failure gone.
        org.mockito.Mockito.reset(businessEventService);

        assertThat(svc.claimOrderForProcessing(ORDER_ID, null))
                .as("a transient failure must not permanently brick the order")
                .isTrue();
        assertThat(svc.isOrderActive(ORDER_ID)).isTrue();
    }

    @Test
    @DisplayName("the DB row is the authority — a row already claimed is rejected")
    void rowAlreadyClaimed_isRejected() {
        when(orderStatusService.markProcessing(any())).thenReturn(false);

        assertThat(svc.claimOrderForProcessing(ORDER_ID, null)).isFalse();
        assertThat(svc.isOrderActive(ORDER_ID))
                .as("rejecting on the row must not record a local claim")
                .isFalse();
    }

    @Test
    @DisplayName("releaseOrderClaim frees a claim the caller could not start")
    void releaseOrderClaim_freesTheOrder() {
        when(orderStatusService.markProcessing(any())).thenReturn(true);
        assertThat(svc.claimOrderForProcessing(ORDER_ID, null)).isTrue();
        assertThat(svc.isOrderActive(ORDER_ID)).isTrue();

        // Simulates the controller's catch: the claim committed but the async
        // submission (or the commit itself) failed.
        svc.releaseOrderClaim(ORDER_ID);

        assertThat(svc.isOrderActive(ORDER_ID)).isFalse();
        assertThat(svc.claimOrderForProcessing(ORDER_ID, null)).isTrue();
    }
}
