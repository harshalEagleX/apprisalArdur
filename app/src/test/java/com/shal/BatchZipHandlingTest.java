package com.shal;

import com.shal.batch.service.BatchService;
import com.shal.common.entity.*;
import com.shal.common.exception.ValidationException;
import com.shal.common.repository.*;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.transaction.support.TransactionTemplate;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * Regression coverage for ZIP intake behavior:
 *
 *  (1) No manifest.json → batch runs without transaction linkage (null transaction)
 *  (2) Valid manifest.json → new AppraisalTransaction created and batch linked
 *  (3) Malformed JSON in manifest.json → non-fatal (no exception, no transaction linked)
 *  (4) manifest.json with is_revision_of → new transaction's revisedFrom is set
 *  (5) ZIP entry with ".." path segment → ValidationException (path traversal blocked)
 */
@SpringBootTest
class BatchZipHandlingTest {

    @Autowired private BatchService batchService;
    @Autowired private ClientRepository clientRepository;
    @Autowired private UserRepository userRepository;
    @Autowired private BatchRepository batchRepository;
    @Autowired private AppraisalTransactionRepository transactionRepository;
    @Autowired private TransactionTemplate tx;

    private long clientId;
    private long userId;
    private String tag;
    private final List<Long> txIdsToCleanup = new ArrayList<>();
    private final List<Long> batchIdsToCleanup = new ArrayList<>();

    @BeforeEach
    void seed() {
        tag = "ZIP_" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        tx.executeWithoutResult(s -> {
            Client c = clientRepository.save(
                    Client.builder().name(tag).code(tag).status("ACTIVE").build());
            clientId = c.getId();
            User u = userRepository.save(User.builder()
                    .username(tag).password("x").role(Role.ADMIN).fullName(tag).build());
            userId = u.getId();
        });
    }

    @AfterEach
    void cleanup() {
        tx.executeWithoutResult(s -> {
            // Batches must be cleaned up before transactions (FK from batch → tx)
            for (Long bid : batchIdsToCleanup) {
                batchRepository.findById(bid).ifPresent(b -> {
                    b.setTransaction(null);     // clear FK before deleting transaction
                    batchRepository.save(b);
                    batchRepository.delete(b);
                });
            }
            for (Long tid : txIdsToCleanup) {
                transactionRepository.findById(tid).ifPresent(transactionRepository::delete);
            }
            userRepository.findByUsername(tag).ifPresent(userRepository::delete);
            clientRepository.findAll().stream()
                    .filter(c -> tag.equals(c.getCode()))
                    .forEach(clientRepository::delete);
        });
    }

    // ── (1) No manifest → no transaction linkage ──────────────────────────────

    @Test
    void noManifest_batchNotLinkedToTransaction() throws Exception {
        Batch batch = seedBatch();
        MockMultipartFile zipFile = makeZip(tag + "_nomfst.zip",
                new String[]{"somefile.txt"}, new String[]{"hello"});

        batchService.linkBatchToTransactionFromManifest(batch, zipFile,
                loadClient());

        Batch reloaded = tx.execute(s -> batchRepository.findById(batch.getId()).orElseThrow());
        assertThat(reloaded.getTransaction())
                .as("No manifest.json in ZIP → transaction must not be linked")
                .isNull();
    }

    // ── (2) Valid manifest → new transaction created and batch linked ─────────

    @Test
    void validManifest_newTransactionCreatedAndLinked() throws Exception {
        Batch batch = seedBatch();
        String txRef = tag + "-TX-001";
        String manifest = "{\"transaction_ref\":\"" + txRef + "\","
                + "\"amc_code\":\"" + tag + "\",\"order_number\":\"ORD-001\","
                + "\"property_address\":\"123 Main St\"}";

        MockMultipartFile zipFile = makeZip(tag + "_mfst.zip",
                new String[]{"manifest.json"}, new String[]{manifest});

        batchService.linkBatchToTransactionFromManifest(batch, zipFile, loadClient());

        // Find the created transaction and register for cleanup
        Batch reloaded = tx.execute(s -> batchRepository.findById(batch.getId()).orElseThrow());
        assertThat(reloaded.getTransaction())
                .as("Valid manifest must link the batch to a new transaction")
                .isNotNull();

        if (reloaded.getTransaction() != null) {
            txIdsToCleanup.add(reloaded.getTransaction().getId());
        }
    }

    // ── (3) Malformed JSON → non-fatal ────────────────────────────────────────

    @Test
    void malformedManifest_nonFatalNoException() throws Exception {
        Batch batch = seedBatch();
        // Deliberately invalid JSON
        MockMultipartFile zipFile = makeZip(tag + "_bad.zip",
                new String[]{"manifest.json"},
                new String[]{"not valid json { broken :"});

        // Must NOT throw — errors in manifest parsing are always non-fatal
        batchService.linkBatchToTransactionFromManifest(batch, zipFile, loadClient());

        Batch reloaded = tx.execute(s -> batchRepository.findById(batch.getId()).orElseThrow());
        assertThat(reloaded.getTransaction())
                .as("Malformed manifest must not link a transaction")
                .isNull();
    }

    // ── (4) is_revision_of → new transaction's revisedFrom is set ───────────

    @Test
    void manifestWithRevision_setsRevisedFromOnNewTransaction() throws Exception {
        // Seed the ORIGINAL (prior) transaction that will be the parent
        String priorRef = tag + "-PRIOR-TX";
        long priorTxId = tx.execute(s -> {
            Client c = clientRepository.findById(clientId).orElseThrow();
            AppraisalTransaction prior = new AppraisalTransaction();
            prior.setTransactionRef(priorRef);
            prior.setAmcCode(tag);
            prior.setOrderNumber("ORD-ORIGINAL");
            prior.setClient(c);
            prior.setStatus(TransactionStatus.RECEIVED);
            prior.setRevisionNumber(0);
            return transactionRepository.save(prior).getId();
        });

        Batch batch = seedBatch();
        // transaction_ref = NEW ref (not in DB) → will create a new transaction.
        // is_revision_of  = PRIOR ref (in DB) → new transaction gets revisedFrom set.
        String newRef = tag + "-REV-TX-001"; // deliberately NOT in DB yet
        String manifest = "{\"transaction_ref\":\"" + newRef + "\","
                + "\"amc_code\":\"" + tag + "\",\"order_number\":\"ORD-REVISION\","
                + "\"is_revision_of\":\"" + priorRef + "\"}";

        MockMultipartFile zipFile = makeZip(tag + "_rev.zip",
                new String[]{"manifest.json"}, new String[]{manifest});

        batchService.linkBatchToTransactionFromManifest(batch, zipFile, loadClient());

        Batch reloaded = tx.execute(s -> batchRepository.findById(batch.getId()).orElseThrow());
        assertThat(reloaded.getTransaction())
                .as("manifest with is_revision_of must link the batch to a new transaction")
                .isNotNull();

        long newTxId = reloaded.getTransaction().getId();
        AppraisalTransaction newTx = tx.execute(s ->
                transactionRepository.findById(newTxId).orElseThrow());

        assertThat(newTx.getRevisedFrom())
                .as("new transaction must have revisedFrom set to the prior transaction")
                .isNotNull();
        assertThat(newTx.getRevisedFrom().getId())
                .as("revisedFrom must point to the seeded prior transaction")
                .isEqualTo(priorTxId);
        assertThat(newTx.getRevisionNumber())
                .as("revision number must be prior + 1")
                .isEqualTo(1);

        // Register both for cleanup in dependency order: new tx first, then prior tx
        txIdsToCleanup.add(0, newTxId);    // new tx (has FK to prior)
        txIdsToCleanup.add(priorTxId);     // prior tx
    }

    // ── (5) Path traversal blocked ────────────────────────────────────────────

    @Test
    void pathTraversalInZip_throwsValidationException() throws Exception {
        Client c = loadClient();
        User u = loadUser();

        // ZIP entry with ".." in the path — this must be rejected
        MockMultipartFile zipFile = makeZip(tag + "_traverse.zip",
                new String[]{"../../etc/passwd"}, new String[]{tag + ":malicious"});

        assertThatThrownBy(() -> batchService.createFromZip(zipFile, c, u))
                .as("ZIP entry with '..' must be rejected as a path traversal attempt")
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("..");

        // createFromZip saves the batch as VALIDATION_FAILED — find and clean it up
        String parentId = tag + "_traverse"; // originalFilename minus ".zip"
        tx.executeWithoutResult(s ->
                batchRepository.findAll().stream()
                        .filter(b -> parentId.equals(b.getParentBatchId()))
                        .forEach(b -> {
                            batchIdsToCleanup.add(b.getId());
                            b.setTransaction(null);
                            batchRepository.delete(b);
                        })
        );
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private Batch seedBatch() {
        return tx.execute(s -> {
            Client c = clientRepository.findById(clientId).orElseThrow();
            User u = userRepository.findById(userId).orElseThrow();
            Batch b = batchRepository.save(Batch.builder()
                    .parentBatchId(tag + "_batch")
                    .client(c).status(BatchStatus.UPLOADED).createdBy(u).build());
            batchIdsToCleanup.add(b.getId());
            return b;
        });
    }

    private Client loadClient() {
        return tx.execute(s -> clientRepository.findById(clientId).orElseThrow());
    }

    private User loadUser() {
        return tx.execute(s -> userRepository.findById(userId).orElseThrow());
    }

    /** Build an in-memory ZIP with the given entry names and content bytes. */
    private static MockMultipartFile makeZip(String filename,
                                              String[] entryNames,
                                              String[] entryContents) throws Exception {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        try (ZipOutputStream zos = new ZipOutputStream(baos)) {
            for (int i = 0; i < entryNames.length; i++) {
                ZipEntry entry = new ZipEntry(entryNames[i]);
                zos.putNextEntry(entry);
                zos.write(entryContents[i].getBytes(StandardCharsets.UTF_8));
                zos.closeEntry();
            }
        }
        return new MockMultipartFile("file", filename, "application/zip", baos.toByteArray());
    }
}
