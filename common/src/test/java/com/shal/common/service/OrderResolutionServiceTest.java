package com.shal.common.service;

import com.shal.common.entity.AppraisalTransaction;
import com.shal.common.entity.Batch;
import com.shal.common.entity.BatchFile;
import com.shal.common.entity.Client;
import com.shal.common.entity.FileType;
import com.shal.common.repository.AppraisalTransactionRepository;
import com.shal.common.repository.BatchFileRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.stubbing.Answer;

import java.lang.reflect.Field;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * Order-resolution linkage. The bug this pins: a single-order ZIP whose engagement
 * letter states a different order number than the appraisal file naming left the
 * engagement unlinked, so the order showed INCOMPLETE despite holding every required
 * document. The single-appraisal-batch fallback attaches such orphans to the sole
 * order — while never fanning out in a multi-order batch.
 */
class OrderResolutionServiceTest {

    private BatchFileRepository batchFileRepository;
    private AppraisalTransactionRepository orderRepository;
    private OrderResolutionService service;

    @BeforeEach
    void setUp() {
        batchFileRepository = mock(BatchFileRepository.class);
        orderRepository = mock(AppraisalTransactionRepository.class);
        BusinessEventService businessEventService = mock(BusinessEventService.class);
        OrderStatusService orderStatusService = mock(OrderStatusService.class);
        service = new OrderResolutionService(batchFileRepository, orderRepository,
                businessEventService, orderStatusService);

        // No cross-batch identity matches — resolution stays within the batch.
        when(batchFileRepository.findByContentHashLinkedToOrder(any())).thenReturn(List.of());
        when(batchFileRepository.findByOrderIdStringAndClientId(any(), any())).thenReturn(List.of());
        when(batchFileRepository.findByPropertySetNameAndClientId(any(), any())).thenReturn(List.of());
        when(batchFileRepository.findActiveByOrderIdAndFileType(any(), any())).thenReturn(List.of());
        when(orderRepository.findByTransactionRef(any())).thenReturn(Optional.empty());
        // save assigns a real id (the entity has no setId — it is DB-generated).
        AtomicLong seq = new AtomicLong(1);
        Answer<AppraisalTransaction> assignId = inv -> {
            AppraisalTransaction t = inv.getArgument(0);
            if (t.getId() == null) setId(t, seq.getAndIncrement());
            return t;
        };
        when(orderRepository.save(any(AppraisalTransaction.class))).thenAnswer(assignId);
    }

    @Test
    void singleOrderBatch_linksMismatchedEngagementToSoleOrder() {
        Client client = client(1L, "EQSOLU");
        Batch batch = new Batch();
        batch.setId(1L);
        batch.setClient(client);
        // Appraisal + its XML share the order number; the engagement uses the generic
        // "EngagementLetter" filename stem that matches nothing — the real failure case.
        BatchFile appraisal  = file(batch, FileType.APPRAISAL,     "660006860.pdf",       "660006860",       "h1");
        BatchFile xml        = file(batch, FileType.APPRAISAL_XML, "660006860.xml",       "660006860",       "h2");
        BatchFile engagement = file(batch, FileType.ENGAGEMENT,    "EngagementLetter.pdf","EngagementLetter","h3");

        service.resolveOrdersForBatch(batch, client, null, Map.of());

        assertThat(appraisal.getOrder()).isNotNull();
        assertThat(xml.getOrder()).isNotNull();
        assertThat(engagement.getOrder())
                .as("engagement must link to the same order despite a mismatched identifier")
                .isNotNull()
                .isSameAs(appraisal.getOrder());
        assertThat(xml.getOrder()).isSameAs(appraisal.getOrder());
    }

    @Test
    void multiOrderBatch_doesNotFanOutOrphans() {
        Client client = client(1L, "EQSOLU");
        Batch batch = new Batch();
        batch.setId(2L);
        batch.setClient(client);
        // Two distinct appraisals → two orders. An orphan engagement matching neither
        // must stay unresolved (manual assignment) rather than be attached arbitrarily.
        BatchFile appraisalA = file(batch, FileType.APPRAISAL,  "111 Oak St.pdf",   "111 Oak St",  "a1");
        BatchFile appraisalB = file(batch, FileType.APPRAISAL,  "222 Elm Ave.pdf",  "222 Elm Ave", "b1");
        BatchFile orphan     = file(batch, FileType.ENGAGEMENT, "EngagementLetter.pdf", "EngagementLetter", "o1");

        service.resolveOrdersForBatch(batch, client, null, Map.of());

        assertThat(appraisalA.getOrder()).isNotNull();
        assertThat(appraisalB.getOrder()).isNotNull();
        assertThat(appraisalA.getOrder().getId()).isNotEqualTo(appraisalB.getOrder().getId());
        assertThat(orphan.getOrder())
                .as("orphan must NOT be attached when the batch anchors multiple orders")
                .isNull();
    }

    @Test
    void backfill_recoversOrphanEngagementWhenAppraisalAlreadyLinked() {
        // The live "stuck INCOMPLETE" case: the appraisal is already linked to an order
        // from an earlier run; only the engagement is orphaned. Backfill must reload the
        // batch's full file set to see the anchoring appraisal and attach the orphan.
        Client client = client(1L, "EQSOLU");
        Batch batch = new Batch();
        batch.setId(3L);
        batch.setClient(client);

        AppraisalTransaction existing = new AppraisalTransaction();
        setId(existing, 42L);
        existing.setTransactionRef("EQSOLU-660006860");

        BatchFile appraisal  = file(batch, FileType.APPRAISAL,  "660006860.pdf",        "660006860",        "h1");
        appraisal.setOrder(existing);                      // already linked
        BatchFile engagement = file(batch, FileType.ENGAGEMENT, "EngagementLetter.pdf", "EngagementLetter", "h3");
        // engagement.order stays null → orphaned

        when(batchFileRepository.findUnresolvedOrderFiles()).thenReturn(List.of(engagement));
        when(batchFileRepository.findByBatchId(3L)).thenReturn(List.of(appraisal, engagement));

        service.backfillUnresolvedFiles(null);

        assertThat(engagement.getOrder())
                .as("backfill must attach the orphan engagement to the appraisal's existing order")
                .isSameAs(existing);
    }

    // ── helpers ──────────────────────────────────────────────────────────────

    private static Client client(long id, String code) {
        Client c = new Client();
        c.setId(id);
        c.setCode(code);
        return c;
    }

    private static BatchFile file(Batch batch, FileType type, String name, String orderId, String hash) {
        BatchFile f = new BatchFile();
        f.setFileType(type);
        f.setFilename(name);
        f.setOrderId(orderId);
        f.setContentHash(hash);
        f.setBatch(batch);
        batch.addFile(f);
        return f;
    }

    private static void setId(AppraisalTransaction t, long id) {
        try {
            Field f = AppraisalTransaction.class.getDeclaredField("id");
            f.setAccessible(true);
            f.set(t, id);
        } catch (ReflectiveOperationException e) {
            throw new RuntimeException(e);
        }
    }
}
