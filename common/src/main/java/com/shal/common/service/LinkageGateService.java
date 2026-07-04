package com.shal.common.service;

import com.shal.common.entity.Batch;
import com.shal.common.entity.BatchFile;
import com.shal.common.entity.FileStatus;
import com.shal.common.entity.FileType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * QC gate G-A: an appraisal must not be QC'd against a false "engagement not
 * provided" when the engagement letter is actually sitting in the same batch,
 * just not linked yet.
 *
 * At intake, {@code DocumentContentSniffer} auto-links a supporting document to
 * an appraisal only when exactly one anchor matches — a tie is left
 * NEEDS_ASSIGNMENT rather than guessed. This service re-runs that same content
 * sniff at QC-run time and reports which appraisals are one of the tied
 * candidates for a still-unresolved document. Those appraisals must be held out
 * of the QC fan-out: running them now would silently record NOT_PROVIDED for a
 * document that is present, producing exactly the false cross-doc VERIFY flood
 * this gate exists to prevent.
 *
 * An appraisal whose engagement/contract is genuinely absent from the batch
 * (no candidate anywhere) is NOT held out — that is the legitimate NOT_PROVIDED
 * path and must proceed normally.
 *
 * The same gate also covers the appraisal MISMO XML (G-A/XML). The XML pairs by
 * basename rather than content sniff, but the failure mode is identical: if an
 * appraisal has no same-set XML while an active-but-unlinked APPRAISAL_XML sits
 * in the batch, running it now drops to PDF-only extraction (no XML overlay) and
 * manufactures the structured-field false positives the XML would have cleared.
 * An appraisal with genuinely no XML anywhere is NOT held — XML is optional and
 * PDF-only is the legitimate path.
 */
@Service
public class LinkageGateService {

    private static final Logger log = LoggerFactory.getLogger(LinkageGateService.class);

    private final DocumentContentSniffer contentSniffer;

    public LinkageGateService(DocumentContentSniffer contentSniffer) {
        this.contentSniffer = contentSniffer;
    }

    /** One appraisal held out of QC, and the unresolved document(s) that plausibly belong to it. */
    public record HeldOutAppraisal(Long appraisalFileId, String appraisalFilename, List<String> candidateFilenames) {}

    /**
     * Appraisals in this batch that must be excluded from a QC run because an
     * active NEEDS_ASSIGNMENT ENGAGEMENT/CONTRACT file scored this appraisal as a
     * tied top candidate during content sniffing. Empty when linkage is fully
     * resolved (or genuinely absent) for every appraisal.
     */
    public List<HeldOutAppraisal> computeHoldOuts(Batch batch) {
        List<BatchFile> appraisals = batch.getFiles().stream()
                .filter(f -> f.getFileType() == FileType.APPRAISAL && f.isActive())
                .toList();
        if (appraisals.isEmpty()) return List.of();

        Map<String, DocumentContentSniffer.OrderIdentity> identityBySet = contentSniffer.extractOrderIdentities(batch);
        Map<String, BatchFile> appraisalBySetKey = new LinkedHashMap<>();
        List<DocumentContentSniffer.Anchor> anchors = new ArrayList<>();
        for (BatchFile a : appraisals) {
            String key = DocumentContentSniffer.setKeyOf(a.getPropertySetName());
            appraisalBySetKey.putIfAbsent(key, a);
            anchors.add(contentSniffer.anchorFor(a, identityBySet.get(key)));
        }

        List<BatchFile> unresolved = batch.getFiles().stream()
                .filter(f -> f.getStatus() == FileStatus.NEEDS_ASSIGNMENT)
                .filter(f -> f.getFileType() == FileType.ENGAGEMENT || f.getFileType() == FileType.CONTRACT)
                .toList();

        Map<Long, List<String>> candidatesByAppraisalId = new LinkedHashMap<>();
        for (BatchFile u : unresolved) {
            String text = contentSniffer.sniffableText(u);
            List<DocumentContentSniffer.SniffMatch> ties = contentSniffer.candidatesAtTopScore(text, anchors);
            if (ties.size() < 2) continue; // no candidate, or a clean single match (should already be linked)
            for (DocumentContentSniffer.SniffMatch m : ties) {
                BatchFile appraisal = appraisalBySetKey.get(m.anchor().setKey());
                if (appraisal == null) continue;
                candidatesByAppraisalId
                        .computeIfAbsent(appraisal.getId(), k -> new ArrayList<>())
                        .add(u.getFilename());
            }
        }

        // ── Appraisal-XML hold-outs (G-A/XML) ──────────────────────────────
        // A set "has its XML" when an active, already-linked APPRAISAL_XML shares
        // an appraisal set key. Orphan XMLs are active APPRAISAL_XML files that are
        // either NEEDS_ASSIGNMENT or landed in a set key no appraisal owns (the
        // basename-divergence orphan the grouper can't auto-pair).
        Set<String> setsWithPairedXml = batch.getFiles().stream()
                .filter(f -> f.getFileType() == FileType.APPRAISAL_XML && f.isActive())
                .filter(f -> f.getStatus() != FileStatus.NEEDS_ASSIGNMENT)
                .map(f -> DocumentContentSniffer.setKeyOf(f.getPropertySetName()))
                .filter(appraisalBySetKey::containsKey)
                .collect(Collectors.toSet());
        List<BatchFile> orphanXml = batch.getFiles().stream()
                .filter(f -> f.getFileType() == FileType.APPRAISAL_XML && f.isActive())
                .filter(f -> f.getStatus() == FileStatus.NEEDS_ASSIGNMENT
                        || !appraisalBySetKey.containsKey(DocumentContentSniffer.setKeyOf(f.getPropertySetName())))
                .toList();
        if (!orphanXml.isEmpty()) {
            List<String> allOrphanNames = orphanXml.stream().map(BatchFile::getFilename).toList();
            for (BatchFile a : appraisals) {
                if (setsWithPairedXml.contains(DocumentContentSniffer.setKeyOf(a.getPropertySetName()))) {
                    continue; // this appraisal already has its paired XML
                }
                // Prefer the basename-matched orphan (the normal case: MAGU96793.XML
                // ↔ MAGU96793.pdf scores 100); fall back to every orphan only when no
                // name matches, so a divergent-name XML still forces a loud HOLD
                // rather than a silent PDF-only run.
                List<String> named = orphanXml.stream()
                        .filter(x -> FileMatchingService.filenameMatchScore(x.getFilename(), a.getFilename()) > 0)
                        .map(BatchFile::getFilename)
                        .toList();
                candidatesByAppraisalId
                        .computeIfAbsent(a.getId(), k -> new ArrayList<>())
                        .addAll(named.isEmpty() ? allOrphanNames : named);
            }
        }

        List<HeldOutAppraisal> heldOut = new ArrayList<>();
        for (BatchFile a : appraisals) {
            List<String> candidates = candidatesByAppraisalId.get(a.getId());
            if (candidates != null && !candidates.isEmpty()) {
                heldOut.add(new HeldOutAppraisal(a.getId(), a.getFilename(), candidates));
            }
        }
        if (!heldOut.isEmpty()) {
            log.info("Batch {} — {} appraisal(s) held out of QC pending linkage resolution: {}",
                    batch.getParentBatchId(), heldOut.size(), heldOut);
        }
        return heldOut;
    }
}
