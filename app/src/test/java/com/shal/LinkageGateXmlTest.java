package com.shal;

import com.shal.common.entity.Batch;
import com.shal.common.entity.BatchFile;
import com.shal.common.entity.FileStatus;
import com.shal.common.entity.FileType;
import com.shal.common.service.DocumentContentSniffer;
import com.shal.common.service.LinkageGateService;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * DB-free coverage for the G-A/XML linkage hold-out.
 *
 * Drives the real {@link LinkageGateService} with {@link BatchFile} entities shaped
 * exactly as the ZIP grouper produces them for the VIKAS multi-order bundle
 * (uploads/VIKAS/4 2/4 — appraisal/*.pdf + appraisal_xml/*.xml, basenames aligned).
 * storagePath points at the real files so the content sniffer runs for real; only
 * propertySetName is set by hand to mirror the grouper's output.
 */
class LinkageGateXmlTest {

    private static final String BASE =
            "/Users/eaglex/Documents/indevelopment/eaglex/SHAL/uploads/VIKAS/4 2/4";

    private final LinkageGateService gate = new LinkageGateService(new DocumentContentSniffer());

    private static BatchFile f(long id, FileType type, String name, String setName,
                               FileStatus status, String storagePath) {
        return BatchFile.builder()
                .id(id).fileType(type).filename(name)
                .propertySetName(setName).status(status).storagePath(storagePath)
                .build();
    }

    private static Batch batchOf(BatchFile... files) {
        Batch b = new Batch();
        b.setParentBatchId("GATE_TEST");
        b.setFiles(new ArrayList<>(List.of(files)));
        return b;
    }

    /** Paired XML (same set as its PDF, basename aligned) → no hold-out. */
    @Test
    void pairedXml_isNotHeldOut() {
        Batch batch = batchOf(
                f(1, FileType.APPRAISAL, "MAGU96793.pdf", "MAGU96793", FileStatus.PENDING,
                        BASE + "/appraisal/MAGU96793.pdf"),
                f(2, FileType.APPRAISAL_XML, "MAGU96793.XML", "MAGU96793", FileStatus.PENDING,
                        BASE + "/appraisal_xml/MAGU96793.XML"));

        assertThat(gate.computeHoldOuts(batch)).isEmpty();
    }

    /** Whole multi-order bundle, every XML basename-paired → no hold-out for any. */
    @Test
    void multiOrderBundle_allPaired_noHoldOuts() {
        Batch batch = batchOf(
                f(1, FileType.APPRAISAL, "MAGU96793.pdf", "MAGU96793", FileStatus.PENDING,
                        BASE + "/appraisal/MAGU96793.pdf"),
                f(2, FileType.APPRAISAL_XML, "MAGU96793.XML", "MAGU96793", FileStatus.PENDING,
                        BASE + "/appraisal_xml/MAGU96793.XML"),
                f(3, FileType.APPRAISAL, "ESCA-0019573.pdf", "ESCA-0019573", FileStatus.PENDING,
                        BASE + "/appraisal/ESCA-0019573.pdf"),
                f(4, FileType.APPRAISAL_XML, "ESCA-0019573.xml", "ESCA-0019573", FileStatus.PENDING,
                        BASE + "/appraisal_xml/ESCA-0019573.xml"),
                f(5, FileType.APPRAISAL, "5807 Fox Hunt Trl.pdf", "5807 Fox Hunt Trl", FileStatus.PENDING,
                        BASE + "/appraisal/5807 Fox Hunt Trl.pdf"),
                f(6, FileType.APPRAISAL_XML, "5807 Fox Hunt Trl.xml", "5807 Fox Hunt Trl", FileStatus.PENDING,
                        BASE + "/appraisal_xml/5807 Fox Hunt Trl.xml"));

        assertThat(gate.computeHoldOuts(batch)).isEmpty();
    }

    /** XML orphaned into the folder-label set (divergent-name failure) → appraisal HELD. */
    @Test
    void orphanedXml_holdsOutTheAppraisal() {
        BatchFile appraisal = f(1, FileType.APPRAISAL, "MAGU96793.pdf", "MAGU96793", FileStatus.PENDING,
                BASE + "/appraisal/MAGU96793.pdf");
        BatchFile orphanXml = f(2, FileType.APPRAISAL_XML, "MAGU96793.XML", "4", FileStatus.PENDING,
                BASE + "/appraisal_xml/MAGU96793.XML"); // set "4" ≠ appraisal set "MAGU96793"

        List<LinkageGateService.HeldOutAppraisal> held = gate.computeHoldOuts(batchOf(appraisal, orphanXml));

        assertThat(held).hasSize(1);
        assertThat(held.get(0).appraisalFileId()).isEqualTo(1L);
        assertThat(held.get(0).candidateFilenames()).contains("MAGU96793.XML");
    }

    /** XML left NEEDS_ASSIGNMENT (never linked) → appraisal HELD. */
    @Test
    void needsAssignmentXml_holdsOutTheAppraisal() {
        BatchFile appraisal = f(1, FileType.APPRAISAL, "MAGU96793.pdf", "MAGU96793", FileStatus.PENDING,
                BASE + "/appraisal/MAGU96793.pdf");
        BatchFile unassignedXml = f(2, FileType.APPRAISAL_XML, "MAGU96793.XML", "MAGU96793",
                FileStatus.NEEDS_ASSIGNMENT, BASE + "/appraisal_xml/MAGU96793.XML");

        List<LinkageGateService.HeldOutAppraisal> held = gate.computeHoldOuts(batchOf(appraisal, unassignedXml));

        assertThat(held).hasSize(1);
        assertThat(held.get(0).appraisalFileId()).isEqualTo(1L);
    }

    /** Genuinely no XML anywhere in the batch → PDF-only is legitimate, NOT held. */
    @Test
    void noXmlAtAll_isNotHeldOut() {
        Batch batch = batchOf(
                f(1, FileType.APPRAISAL, "MAGU96793.pdf", "MAGU96793", FileStatus.PENDING,
                        BASE + "/appraisal/MAGU96793.pdf"));

        assertThat(gate.computeHoldOuts(batch)).isEmpty();
    }
}
