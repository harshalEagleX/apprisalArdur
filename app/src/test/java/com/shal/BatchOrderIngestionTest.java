package com.shal;

import com.shal.batch.service.BatchService;
import com.shal.common.entity.*;
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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.stream.Collectors;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import com.shal.common.exception.BatchStructureException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * End-to-end coverage for the redesigned ZIP intake → order-grouping → order-linking
 * flow. Each test uploads a ZIP shaped like one of the real folder layouts the system
 * must accept and asserts that every document ends up linked to the correct Order
 * (BatchFile.order), closing the Batch-view / Order-view mismatch.
 */
@SpringBootTest
class BatchOrderIngestionTest {

    @Autowired private BatchService batchService;
    @Autowired private ClientRepository clientRepository;
    @Autowired private UserRepository userRepository;
    @Autowired private BatchRepository batchRepository;
    @Autowired private BatchFileRepository batchFileRepository;
    @Autowired private AppraisalTransactionRepository orderRepository;
    @Autowired private com.shal.common.service.OrderDeletionService orderDeletionService;
    @Autowired private com.shal.qc.controller.api.QCApiController qcApiController;
    @Autowired private TransactionTemplate tx;

    private long clientId;
    private long userId;
    private String tag;
    private final List<Long> batchIdsToCleanup = new ArrayList<>();

    @BeforeEach
    void authAdmin() {
        // QCApiController is @PreAuthorize("hasRole('ADMIN')") — the AOP proxy needs an auth.
        org.springframework.security.core.context.SecurityContextHolder.getContext().setAuthentication(
                new org.springframework.security.authentication.UsernamePasswordAuthenticationToken(
                        "admin", "x",
                        List.of(new org.springframework.security.core.authority.SimpleGrantedAuthority("ROLE_ADMIN"))));
    }

    @BeforeEach
    void seed() {
        tag = "ORD_" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
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
        org.springframework.security.core.context.SecurityContextHolder.clearContext();
        for (Long bid : batchIdsToCleanup) {
            try { batchService.deleteBatch(bid); } catch (Exception ignored) { }
        }
        // User/client are referenced by audit_log rows the upload wrote — leaving the
        // tagged rows behind is harmless test data; deleting them would trip FK guards.
    }

    // ── (1) Structured single-order ZIP: appraisal + xml + contract + engagement,
    //        each in its own type folder under one order folder. All four must link
    //        to ONE order (this is the exact screenshot mismatch case). ────────────
    @Test
    void structuredSingleOrder_allDocsLinkToOneOrder() {
        MockMultipartFile zip = makeZip(tag + "_structured.zip", Map.of(
                "VIKAS/1/1/appraisal/ESCA-0019573.pdf", pdf(),
                "VIKAS/1/1/appraisal_xml/ESCA-0019573.xml", mismoXml(),
                "VIKAS/1/1/contract/1_Purchase_Contract_Stanford_exe.pdf", pdf(),
                "VIKAS/1/1/engagement/EngagementLetter 2.pdf", pdf()));

        Long batchId = upload(zip);
        List<DocView> docs = docsOf(batchId);

        assertThat(docs).hasSize(4);
        assertThat(docs).allSatisfy(d ->
                assertThat(d.orderId).as("every doc must be linked to an order: " + d.filename).isNotNull());
        assertThat(distinctOrders(docs)).as("all four docs share one order").hasSize(1);
        assertThat(typesLinkedTo(docs, docs.get(0).orderId))
                .contains(FileType.APPRAISAL, FileType.APPRAISAL_XML, FileType.CONTRACT, FileType.ENGAGEMENT);
        assertThat(docs).noneMatch(d -> d.status == FileStatus.NEEDS_ASSIGNMENT);
    }

    // ── (2) Flat order ZIP: no type folders, files dumped in a numbered folder.
    //        Classification must fall back to filename/content so nothing is dropped. ─
    @Test
    void flatOrderZip_classifiedByFilename_allLink() {
        MockMultipartFile zip = makeZip(tag + "_flat.zip", Map.of(
                "xml1/1/ESCA-0019573.pdf", pdf(),
                "xml1/1/ESCA-0019573.xml", mismoXml(),
                "xml1/1/1_Purchase_Contract_Stanford_exe.pdf", pdf(),
                "xml1/1/EngagementLetter 2.pdf", pdf()));

        Long batchId = upload(zip);
        List<DocView> docs = docsOf(batchId);

        assertThat(docs).as("flat folder files must not be dropped").hasSize(4);
        assertThat(typesOf(docs)).contains(
                FileType.APPRAISAL, FileType.APPRAISAL_XML, FileType.CONTRACT, FileType.ENGAGEMENT);
        assertThat(distinctOrders(docs)).hasSize(1);
        assertThat(docs).allSatisfy(d -> assertThat(d.orderId).isNotNull());
    }

    // ── (3) Multi-property batch: several appraisals + contracts share ONE type
    //        folder. Must split into one order per property by filename. ───────────
    @Test
    void multiPropertyOneTypeFolder_splitsByFilename() {
        MockMultipartFile zip = makeZip(tag + "_multi.zip", Map.of(
                "EQSS/xBatch/appraisal/2307 Merrily Cir N.pdf", pdf(),
                "EQSS/xBatch/appraisal/8234 E Pearson.pdf", pdf(),
                "EQSS/xBatch/contract/2307 Merrily CONTRACT.pdf", pdf(),
                "EQSS/xBatch/contract/8234 E Pearson Purchase-agreement.pdf", pdf()));

        Long batchId = upload(zip);
        List<DocView> docs = docsOf(batchId);

        assertThat(docs).hasSize(4);
        assertThat(distinctOrders(docs)).as("two properties → two orders").hasSize(2);
        // Each order must hold exactly one appraisal and one contract.
        Map<Long, List<DocView>> byOrder = docs.stream()
                .filter(d -> d.orderId != null)
                .collect(Collectors.groupingBy(d -> d.orderId));
        assertThat(byOrder).hasSize(2);
        byOrder.forEach((order, group) -> {
            assertThat(group).hasSize(2);
            assertThat(typesOf(group)).containsExactlyInAnyOrder(FileType.APPRAISAL, FileType.CONTRACT);
        });
    }

    // ── (4) Nested order ZIP inside the batch ZIP must be unpacked and linked. ────
    @Test
    void nestedOrderZip_isUnpackedAndLinked() {
        byte[] innerZip = rawZip(Map.of(
                "appraisal/ESCA-0019573.pdf", pdf(),
                "engagement/EngagementLetter 2.pdf", pdf()));
        MockMultipartFile zip = makeZip(tag + "_nested.zip", Map.of(
                "orders/1.zip", innerZip));

        Long batchId = upload(zip);
        List<DocView> docs = docsOf(batchId);

        assertThat(docs).as("nested-zip contents must be extracted").hasSize(2);
        assertThat(typesOf(docs)).contains(FileType.APPRAISAL, FileType.ENGAGEMENT);
        assertThat(distinctOrders(docs)).hasSize(1);
        assertThat(docs).allSatisfy(d -> assertThat(d.orderId).isNotNull());
    }

    // ── (5) Soft-deleting a batch must remove its orphaned Order (no ghost order
    //        left behind pointing at documents that no longer exist). ─────────────
    @Test
    void softDeletingBatch_removesOrphanedOrder() {
        MockMultipartFile zip = makeZip(tag + "_delete.zip", Map.of(
                "VIKAS/1/1/appraisal/ESCA-0019573.pdf", pdf(),
                "VIKAS/1/1/appraisal_xml/ESCA-0019573.xml", mismoXml(),
                "VIKAS/1/1/contract/1_Purchase_Contract_Stanford_exe.pdf", pdf(),
                "VIKAS/1/1/engagement/EngagementLetter 2.pdf", pdf()));

        Long batchId = upload(zip);
        List<DocView> docs = docsOf(batchId);
        Long orderId = distinctOrders(docs).get(0);
        assertThat(orderId).isNotNull();
        boolean existsBefore = Boolean.TRUE.equals(tx.execute(s -> orderRepository.findById(orderId).isPresent()));
        assertThat(existsBefore).isTrue();

        tx.executeWithoutResult(s -> batchService.softDeleteBatch(batchId, userId));

        boolean existsAfter = Boolean.TRUE.equals(tx.execute(s -> orderRepository.findById(orderId).isPresent()));
        assertThat(existsAfter)
                .as("soft-deleting the only batch must delete the now-orphaned order")
                .isFalse();
    }

    // ── Structural gate — malformed uploads are rejected at intake ────────────────

    // (6) A stray non-PDF/non-XML file rejects the whole ZIP with a fixable issue.
    @Test
    void unsupportedFileType_rejectsUpload() {
        MockMultipartFile zip = makeZip(tag + "_bad_ext.zip", Map.of(
                "MAGU96793/appraisal/MAGU96793.pdf", pdf(),
                "MAGU96793/appraisal/MAGU96793.xml", mismoXml(),
                "MAGU96793/appraisal/scanner-notes.docx", pdf()));

        assertThatThrownBy(() -> createFromZipTx(zip))
                .isInstanceOf(BatchStructureException.class)
                .satisfies(e -> assertThat(((BatchStructureException) e).getIssues())
                        .anySatisfy(i -> assertThat(i).contains("scanner-notes.docx")));
    }

    // (7) An XML whose basename doesn't match its appraisal PDF is rejected.
    @Test
    void xmlNameMismatch_rejectsUpload() {
        MockMultipartFile zip = makeZip(tag + "_bad_xml.zip", Map.of(
                "MAGU96793/appraisal/MAGU96793.pdf", pdf(),
                "MAGU96793/appraisal/report.xml", mismoXml()));

        assertThatThrownBy(() -> createFromZipTx(zip))
                .isInstanceOf(BatchStructureException.class)
                .satisfies(e -> assertThat(((BatchStructureException) e).getIssues())
                        .anySatisfy(i -> assertThat(i).contains("report.xml")));
    }

    // (8) A ZIP with no appraisal PDF at all is rejected.
    @Test
    void noAppraisalPdf_rejectsUpload() {
        MockMultipartFile zip = makeZip(tag + "_no_appraisal.zip", Map.of(
                "MAGU96793/engagement/EngagementLetter.pdf", pdf(),
                "MAGU96793/contract/purchase contract.pdf", pdf()));

        assertThatThrownBy(() -> createFromZipTx(zip))
                .isInstanceOf(BatchStructureException.class)
                .satisfies(e -> assertThat(((BatchStructureException) e).getIssues())
                        .anySatisfy(i -> assertThat(i).contains("No appraisal PDF")));
    }

    // (9) A well-formed order with a name-matched XML passes the gate cleanly.
    @Test
    void wellFormedOrderWithXml_isAccepted() {
        MockMultipartFile zip = makeZip(tag + "_good.zip", Map.of(
                "MAGU96793/appraisal/MAGU96793.pdf", pdf(),
                "MAGU96793/appraisal/MAGU96793.xml", mismoXml(),
                "MAGU96793/contract/purchase contract.pdf", pdf(),
                "MAGU96793/engagement/EngagementLetter.pdf", pdf()));

        Long batchId = upload(zip);
        assertThat(docsOf(batchId)).hasSize(4);
    }

    // (10) Hard-deleting an order removes the order row and all of its documents.
    @Test
    void hardDeleteOrder_removesOrderAndItsDocuments() {
        MockMultipartFile zip = makeZip(tag + "_del.zip", Map.of(
                "MAGU96793/appraisal/MAGU96793.pdf", pdf(),
                "MAGU96793/appraisal/MAGU96793.xml", mismoXml(),
                "MAGU96793/engagement/EngagementLetter.pdf", pdf()));
        Long batchId = upload(zip);
        Long orderId = distinctOrders(docsOf(batchId)).get(0);
        assertThat(orderId).isNotNull();

        int removed = tx.execute(s -> orderDeletionService.hardDeleteOrder(orderId));

        assertThat(removed).as("documents removed").isGreaterThanOrEqualTo(2);
        boolean orderGone = Boolean.TRUE.equals(tx.execute(s -> orderRepository.findById(orderId).isEmpty()));
        assertThat(orderGone).as("order row deleted").isTrue();
        assertThat(docsOf(batchId)).as("no files remain linked to the deleted order")
                .noneMatch(d -> orderId.equals(d.orderId));
    }

    // (11) QC is refused for an order missing required docs (here: no XML, no engagement).
    @Test
    void qcRefused_whenOrderMissingRequiredDocs() {
        MockMultipartFile zip = makeZip(tag + "_incomplete.zip", Map.of(
                "MAGU96793/appraisal/MAGU96793.pdf", pdf()));
        Long batchId = upload(zip);
        Long orderId = distinctOrders(docsOf(batchId)).get(0);
        assertThat(orderId).isNotNull();

        org.springframework.http.ResponseEntity<Map<String, Object>> resp =
                tx.execute(s -> qcApiController.processOrder(orderId, null));

        assertThat(resp.getStatusCode().value()).as("QC must be refused for an incomplete order").isEqualTo(400);
        assertThat(String.valueOf(resp.getBody().get("incompleteOrders")))
                .contains("Appraisal XML").contains("Engagement letter");
    }

    // ── Helpers ──────────────────────────────────────────────────────────────────

    private void createFromZipTx(MockMultipartFile zip) {
        tx.executeWithoutResult(s -> {
            Client c = clientRepository.findById(clientId).orElseThrow();
            User u = userRepository.findById(userId).orElseThrow();
            batchService.createFromZip(zip, c, u);
        });
    }

    private Long upload(MockMultipartFile zip) {
        return tx.execute(s -> {
            Client c = clientRepository.findById(clientId).orElseThrow();
            User u = userRepository.findById(userId).orElseThrow();
            Batch b = batchService.createFromZip(zip, c, u);
            batchIdsToCleanup.add(b.getId());
            return b.getId();
        });
    }

    private record DocView(String filename, FileType fileType, FileStatus status, Long orderId) {}

    private List<DocView> docsOf(Long batchId) {
        return tx.execute(s -> batchFileRepository.findAll().stream()
                .filter(f -> f.getBatch() != null && batchId.equals(f.getBatch().getId()))
                .map(f -> new DocView(f.getFilename(), f.getFileType(), f.getStatus(),
                        f.getOrder() != null ? f.getOrder().getId() : null))
                .toList());
    }

    private static List<Long> distinctOrders(List<DocView> docs) {
        return docs.stream().map(DocView::orderId).filter(Objects::nonNull).distinct().toList();
    }

    private static List<FileType> typesOf(List<DocView> docs) {
        return docs.stream().map(DocView::fileType).toList();
    }

    private static List<FileType> typesLinkedTo(List<DocView> docs, Long orderId) {
        return docs.stream().filter(d -> orderId.equals(d.orderId)).map(DocView::fileType).toList();
    }

    private static byte[] pdf() {
        return ("%PDF-1.4\n dummy " + UUID.randomUUID()).getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] mismoXml() {
        return ("<?xml version=\"1.0\"?><VALUATION_RESPONSE xmlns=\"MISMO\">"
                + UUID.randomUUID() + "</VALUATION_RESPONSE>").getBytes(StandardCharsets.UTF_8);
    }

    private static MockMultipartFile makeZip(String filename, Map<String, byte[]> entries) {
        return new MockMultipartFile("file", filename, "application/zip", rawZip(entries));
    }

    private static byte[] rawZip(Map<String, byte[]> entries) {
        // Preserve insertion order for deterministic extraction.
        Map<String, byte[]> ordered = new LinkedHashMap<>(entries);
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        try (ZipOutputStream zos = new ZipOutputStream(baos)) {
            for (Map.Entry<String, byte[]> e : ordered.entrySet()) {
                zos.putNextEntry(new ZipEntry(e.getKey()));
                zos.write(e.getValue());
                zos.closeEntry();
            }
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
        return baos.toByteArray();
    }
}
