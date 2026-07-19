package com.shal.common.service;

import com.shal.common.entity.AppraisalTransaction;
import com.shal.common.entity.OrderDocumentStatus;
import com.shal.common.repository.AppraisalTransactionRepository;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.repository.QCResultRepository;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

/**
 * markProcessing must claim the order via the ATOMIC conditional UPDATE
 * (claimForQcIfNotProcessing), not a read-then-write — so two nodes can't both
 * launch a QC run for the same order. rows==1 → we won the claim; rows==0 → someone
 * else holds it. Regression guard for PRODUCTION_GAPS J1.
 */
class OrderStatusServiceMarkProcessingTest {

    private OrderStatusService service(AppraisalTransactionRepository repo) {
        return new OrderStatusService(mock(BatchFileRepository.class),
                mock(QCResultRepository.class), repo);
    }

    private static AppraisalTransaction order(long id) {
        AppraisalTransaction t = new AppraisalTransaction();
        try {
            Field f = AppraisalTransaction.class.getDeclaredField("id");
            f.setAccessible(true);
            f.set(t, id);
        } catch (ReflectiveOperationException e) {
            throw new RuntimeException(e);
        }
        return t;
    }

    @Test
    void winsClaimWhenUpdateAffectsOneRow_viaAtomicUpdateNotSave() {
        AppraisalTransactionRepository repo = mock(AppraisalTransactionRepository.class);
        when(repo.claimForQcIfNotProcessing(eq(1L), any(LocalDateTime.class))).thenReturn(1);

        AppraisalTransaction o = order(1L);
        assertThat(service(repo).markProcessing(o)).isTrue();

        verify(repo).claimForQcIfNotProcessing(eq(1L), any(LocalDateTime.class));
        verify(repo, never()).save(any());                       // NOT a read-then-write
        assertThat(o.getDocumentStatus()).isEqualTo(OrderDocumentStatus.QC_PROCESSING);
    }

    @Test
    void losesClaimWhenAnotherNodeAlreadyHoldsIt() {
        AppraisalTransactionRepository repo = mock(AppraisalTransactionRepository.class);
        when(repo.claimForQcIfNotProcessing(eq(2L), any(LocalDateTime.class))).thenReturn(0);

        assertThat(service(repo).markProcessing(order(2L))).isFalse();
        verify(repo, never()).save(any());
    }

    @Test
    void rejectsNullOrTransientOrder() {
        AppraisalTransactionRepository repo = mock(AppraisalTransactionRepository.class);
        assertThat(service(repo).markProcessing(null)).isFalse();
        assertThat(service(repo).markProcessing(new AppraisalTransaction())).isFalse(); // no id
        verify(repo, never()).claimForQcIfNotProcessing(any(), any());
    }
}
