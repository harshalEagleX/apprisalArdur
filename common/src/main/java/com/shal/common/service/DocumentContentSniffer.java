package com.shal.common.service;

import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Content-ID sniffing for intake linkage (pipeline stage S3).
 *
 * Engagement letters and purchase contracts state — inside the document — the
 * AMC order/file number and the subject property address. When the ZIP layout
 * gives no structural evidence (the file is not co-located with an appraisal),
 * this service reads the first pages of the PDF and matches those identifiers
 * against the batch's appraisal anchors:
 *
 *   order-number exact hit  → 0.95 confidence
 *   subject-address hit     → 0.85 confidence
 *
 * A match is only returned when exactly one anchor wins — two anchors matching
 * equally is ambiguity, which must go to manual assignment, never a guess.
 *
 * Everything here is best-effort and must never fail intake: unreadable or
 * image-only PDFs simply yield no text and therefore no match.
 */
@Service
public class DocumentContentSniffer {

    private static final Logger log = LoggerFactory.getLogger(DocumentContentSniffer.class);

    /** Pages to read — order number + address are on page 1 of every engagement template. */
    private static final int MAX_PAGES = 3;
    private static final long MAX_PDF_BYTES = 60L * 1024 * 1024;

    public static final double CONFIDENCE_ORDER_NUMBER = 0.95;
    public static final double CONFIDENCE_ADDRESS = 0.85;

    /**
     * Order identity extracted from a MISMO appraisal XML: the AMC/lender order
     * number and the subject property address. Either field may be null.
     */
    public record OrderIdentity(String orderNumber, String propertyAddress) {
        public boolean isEmpty() { return orderNumber == null && propertyAddress == null; }
    }

    /** One appraisal the sniffer can link supporting documents to. */
    public record Anchor(String setKey,
                         String displayName,
                         Set<String> orderNumberTokens,
                         List<String> addressKeys) {}

    /** A successful content match against a single unambiguous anchor. */
    public record SniffMatch(Anchor anchor, double confidence, String reason) {}

    // ── PDF text extraction ─────────────────────────────────────────────────

    /**
     * Text of the first {@value #MAX_PAGES} pages, or "" when the PDF is
     * unreadable/encrypted/image-only. Never throws.
     */
    public String extractPdfText(Path pdfPath) {
        try {
            if (pdfPath == null || !Files.exists(pdfPath) || Files.size(pdfPath) > MAX_PDF_BYTES) {
                return "";
            }
            try (PDDocument doc = Loader.loadPDF(pdfPath.toFile())) {
                PDFTextStripper stripper = new PDFTextStripper();
                stripper.setStartPage(1);
                stripper.setEndPage(Math.min(MAX_PAGES, doc.getNumberOfPages()));
                String text = stripper.getText(doc);
                return text != null ? text : "";
            }
        } catch (Exception e) {
            log.debug("PDF text extraction failed for {}: {}", pdfPath, e.getMessage());
            return "";
        }
    }

    // ── Document-type content heuristic ─────────────────────────────────────

    /** Weighted contract markers (cover the "Offer Summary", "Purchase Agreement",
     *  and REPC formats seen in the corpus). */
    private static final List<Map.Entry<String, Double>> CONTRACT_MARKERS = List.of(
            Map.entry("offer to purchase", 3.0), Map.entry("offer summary", 3.0),
            Map.entry("purchase agreement", 3.0), Map.entry("purchase and sale", 3.0),
            Map.entry("real estate purchase", 3.0), Map.entry("sales price", 2.5),
            Map.entry("purchase price", 2.5), Map.entry("earnest money", 2.5),
            Map.entry("emd amount", 2.5), Map.entry("seller's concession", 2.0),
            Map.entry("close by date", 2.0), Map.entry("closing date", 2.0),
            Map.entry("financing contingency", 2.0), Map.entry("listing agent", 1.5),
            Map.entry("buyer's agent", 1.5), Map.entry("title company", 1.5),
            Map.entry("escrow", 1.5));

    /** Engagement-letter counter-markers — presence pulls a document back toward
     *  "engagement" so a real order form is never mistaken for a contract. */
    private static final List<Map.Entry<String, Double>> ENGAGEMENT_MARKERS = List.of(
            Map.entry("service fee", 3.0), Map.entry("intended use", 2.0),
            Map.entry("file id", 3.0), Map.entry("order number", 2.0),
            Map.entry("appraiser:", 2.0), Map.entry("due date", 2.0),
            Map.entry("assigned:", 2.0));

    /** Minimum contract score (also must exceed the engagement score) to reclassify. */
    public static final double CONTRACT_MARKER_THRESHOLD = 6.0;

    /**
     * Heuristic: does this document body read like a purchase/sales contract rather
     * than an engagement letter? Used to correct a mis-filed document — e.g. an
     * "Offer to Purchase" dropped into the AMC's engagement folder — so it is not
     * counted as a second engagement letter. Requires several strong contract
     * markers AND a clear margin over engagement markers; validated on the corpus
     * (real contract scored 14.5, real engagement letters 0–4.5) so a real order
     * form is never reclassified. Contracts are never QC-read, so the only effect
     * of a match is dropping the document from QC — deliberately conservative.
     */
    public boolean looksLikeSalesContract(String text) {
        if (text == null || text.isBlank()) return false;
        String t = text.toLowerCase();
        double contract = 0.0;
        for (Map.Entry<String, Double> m : CONTRACT_MARKERS) {
            if (t.contains(m.getKey())) contract += m.getValue();
        }
        double engagement = 0.0;
        for (Map.Entry<String, Double> m : ENGAGEMENT_MARKERS) {
            if (t.contains(m.getKey())) engagement += m.getValue();
        }
        return contract >= CONTRACT_MARKER_THRESHOLD && contract > engagement;
    }

    // ── MISMO XML identity ──────────────────────────────────────────────────

    private static final Pattern XML_ORDER_ID = Pattern.compile(
            "(?i)(?:AppraiserFile|LenderCase|InternalOrder|CaseFile|Order|_?Case)[A-Za-z_]*Identifier\\s*=\\s*\"([^\"]{4,40})\"");
    private static final Pattern XML_STREET = Pattern.compile(
            "(?i)_?StreetAddress\\s*=\\s*\"([^\"]{4,120})\"");
    private static final Pattern XML_STREET_ELEMENT = Pattern.compile(
            "(?i)<(?:[A-Za-z]+:)?StreetAddress>\\s*([^<]{4,120})\\s*<");

    /**
     * Extract the AMC order number and subject address from a MISMO appraisal
     * XML. Attribute-style (MISMO 2.6) and element-style layouts are both
     * tried; nulls when the file carries neither. Never throws.
     */
    public OrderIdentity parseMismoIdentity(Path xmlPath) {
        try {
            if (xmlPath == null || !Files.exists(xmlPath)) return new OrderIdentity(null, null);
            byte[] bytes = Files.readAllBytes(xmlPath);
            String xml = new String(bytes, 0, Math.min(bytes.length, 512 * 1024), StandardCharsets.UTF_8);

            String orderNumber = firstGroup(XML_ORDER_ID, xml);
            String street = firstGroup(XML_STREET, xml);
            if (street == null) street = firstGroup(XML_STREET_ELEMENT, xml);
            return new OrderIdentity(clean(orderNumber), clean(street));
        } catch (Exception e) {
            log.debug("MISMO identity parse failed for {}: {}", xmlPath, e.getMessage());
            return new OrderIdentity(null, null);
        }
    }

    // ── Anchors / sniffable text for a BatchFile ────────────────────────────

    /** setKey helper — an order group's map key: its propertySetName, or "__root__". */
    public static String setKeyOf(String propertySetName) {
        return propertySetName != null && !propertySetName.isBlank() ? propertySetName : "__root__";
    }

    /**
     * Build the anchor identity for one appraisal: order-number tokens and address
     * keys drawn from its orderId, filename, and (when available) its group's MISMO
     * XML identity. Shared by intake auto-linking and the QC linkage gate so both
     * score candidates identically.
     */
    public Anchor anchorFor(com.shal.common.entity.BatchFile appraisal, OrderIdentity identity) {
        String base = baseNameNoExt(appraisal.getFilename());
        Set<String> idTokens = anchorIdTokens(appraisal.getOrderId(), base,
                identity != null ? identity.orderNumber() : null);
        List<String> addressKeys = new ArrayList<>();
        String filenameKey = addressKey(appraisal.getFilename());
        if (filenameKey != null && !filenameKey.isBlank()) addressKeys.add(filenameKey);
        if (identity != null && identity.propertyAddress() != null) {
            String xmlKey = addressKey(identity.propertyAddress());
            if (xmlKey != null && !xmlKey.isBlank() && !addressKeys.contains(xmlKey)) addressKeys.add(xmlKey);
        }
        String display = appraisal.getPropertySetName() != null && !appraisal.getPropertySetName().isBlank()
                ? appraisal.getPropertySetName() : base;
        return new Anchor(setKeyOf(appraisal.getPropertySetName()), display, idTokens, addressKeys);
    }

    /**
     * The text a document can be identified by: PDF page text for PDFs, or the
     * order-number/address fields for a MISMO XML (its own identity, since XML
     * carries no free-text body to scan). Never throws.
     */
    public String sniffableText(com.shal.common.entity.BatchFile file) {
        if (file.getStoragePath() == null) return "";
        Path path = Path.of(file.getStoragePath());
        if (file.getFileType() == com.shal.common.entity.FileType.APPRAISAL_XML) {
            OrderIdentity identity = parseMismoIdentity(path);
            return (identity.orderNumber() != null ? identity.orderNumber() + " " : "")
                    + (identity.propertyAddress() != null ? identity.propertyAddress() : "");
        }
        return extractPdfText(path);
    }

    /**
     * Each order group's true identity (AMC order number + subject address) read
     * from its MISMO appraisal XML — keyed by {@link #setKeyOf}. Groups without an
     * XML, or whose XML carries neither field, are absent. Shared by intake (once,
     * at upload) and the QC linkage gate (recomputed live at QC-run time, since the
     * gate has no persisted copy of intake's transient identity map).
     */
    public Map<String, OrderIdentity> extractOrderIdentities(com.shal.common.entity.Batch batch) {
        Map<String, OrderIdentity> identities = new java.util.HashMap<>();
        for (com.shal.common.entity.BatchFile f : batch.getFiles()) {
            if (f.getFileType() != com.shal.common.entity.FileType.APPRAISAL_XML || f.getStoragePath() == null) continue;
            OrderIdentity identity = parseMismoIdentity(Path.of(f.getStoragePath()));
            if (!identity.isEmpty()) {
                identities.putIfAbsent(setKeyOf(f.getPropertySetName()), identity);
            }
        }
        return identities;
    }

    private static String baseNameNoExt(String filename) {
        if (filename == null) return null;
        String n = filename;
        int slash = Math.max(n.lastIndexOf('/'), n.lastIndexOf('\\'));
        if (slash >= 0) n = n.substring(slash + 1);
        int dot = n.lastIndexOf('.');
        return (dot > 0 ? n.substring(0, dot) : n).trim();
    }

    // ── Matching ────────────────────────────────────────────────────────────

    /**
     * Match extracted document text against the batch's appraisal anchors.
     * Returns a match only when exactly one anchor scores highest — ties are
     * ambiguous and stay unlinked for manual assignment.
     */
    public Optional<SniffMatch> match(String documentText, List<Anchor> anchors) {
        List<SniffMatch> best = candidatesAtTopScore(documentText, anchors);
        if (best.size() == 1) {
            return Optional.of(best.get(0));
        }
        if (best.size() > 1) {
            log.info("Content sniff ambiguous: {} anchors matched at {} — leaving unlinked for manual assignment",
                    best.size(), best.get(0).confidence());
        }
        return Optional.empty();
    }

    /**
     * Every anchor that scored the single highest confidence for this text — empty
     * when nothing matched, one entry for a clean match, several when tied
     * (ambiguous). Used both by {@link #match} (intake auto-link, ties → unlinked)
     * and by the QC linkage gate, which needs to know an appraisal is one of the
     * tied candidates even though intake could not pick it automatically.
     */
    public List<SniffMatch> candidatesAtTopScore(String documentText, List<Anchor> anchors) {
        if (documentText == null || documentText.isBlank() || anchors == null || anchors.isEmpty()) {
            return List.of();
        }
        Set<String> textIdTokens = orderNumberTokens(documentText);
        String normalizedText = normalizeText(documentText);

        List<SniffMatch> best = new ArrayList<>();
        double bestScore = 0;
        for (Anchor anchor : anchors) {
            SniffMatch m = scoreAnchor(anchor, textIdTokens, normalizedText);
            if (m == null) continue;
            if (m.confidence() > bestScore) {
                bestScore = m.confidence();
                best.clear();
                best.add(m);
            } else if (m.confidence() == bestScore) {
                best.add(m);
            }
        }
        return best;
    }

    private SniffMatch scoreAnchor(Anchor anchor, Set<String> textIdTokens, String normalizedText) {
        for (String anchorToken : anchor.orderNumberTokens()) {
            if (textIdTokens.contains(anchorToken)
                    || normalizedIdText(normalizedText).contains(anchorToken)) {
                return new SniffMatch(anchor, CONFIDENCE_ORDER_NUMBER,
                        "order number \"" + anchorToken + "\" found in document text");
            }
        }
        for (String addressKey : anchor.addressKeys()) {
            if (addressKeyPresent(addressKey, normalizedText)) {
                return new SniffMatch(anchor, CONFIDENCE_ADDRESS,
                        "subject address \"" + addressKey + "\" found in document text");
            }
        }
        return null;
    }

    /**
     * True when every token of the normalized address key appears in the text,
     * including its street number — a name-only overlap is not an address hit.
     */
    static boolean addressKeyPresent(String addressKey, String normalizedText) {
        if (addressKey == null || addressKey.isBlank()) return false;
        String[] tokens = addressKey.trim().split("\\s+");
        boolean hasNumber = false;
        for (String token : tokens) {
            if (token.isBlank()) continue;
            if (!containsToken(normalizedText, token)) return false;
            if (token.chars().allMatch(Character::isDigit)) hasNumber = true;
        }
        return hasNumber && tokens.length >= 2;
    }

    private static boolean containsToken(String normalizedText, String token) {
        int idx = normalizedText.indexOf(token);
        while (idx >= 0) {
            boolean startOk = idx == 0 || normalizedText.charAt(idx - 1) == ' ';
            int end = idx + token.length();
            boolean endOk = end == normalizedText.length() || normalizedText.charAt(end) == ' ';
            if (startOk && endOk) return true;
            idx = normalizedText.indexOf(token, idx + 1);
        }
        return false;
    }

    // ── Token helpers ───────────────────────────────────────────────────────

    private static final Pattern ID_TOKEN = Pattern.compile(
            "\\b([A-Za-z]{2,8}[-_ ]?\\d{4,12}|\\d{6,14})\\b");

    /**
     * ID-shaped tokens in a string (e.g. "ESCA-0019573", "2024-1187765", long
     * digit runs), normalized to uppercase with separators removed so
     * "ESCA 0019573" and "esca-0019573" compare equal.
     */
    public static Set<String> orderNumberTokens(String text) {
        Set<String> tokens = new LinkedHashSet<>();
        if (text == null || text.isBlank()) return tokens;
        Matcher m = ID_TOKEN.matcher(text);
        while (m.find()) {
            String norm = normalizeIdToken(m.group(1));
            if (norm != null) tokens.add(norm);
        }
        return tokens;
    }

    /** Uppercase, separators stripped. Null for tokens too short to be identifying. */
    public static String normalizeIdToken(String raw) {
        if (raw == null) return null;
        String norm = raw.toUpperCase().replaceAll("[-_ ]", "");
        return norm.length() >= 6 ? norm : null;
    }

    /** Lowercased text with all non-alphanumerics collapsed to single spaces. */
    public static String normalizeText(String text) {
        if (text == null) return "";
        return text.toLowerCase().replaceAll("[^a-z0-9]+", " ").trim();
    }

    /** The normalized text with spaces removed inside letter→digit runs, for ID lookup. */
    private static String normalizedIdText(String normalizedText) {
        // "esca 0019573" → also match anchor token "ESCA0019573" (lowercased here)
        return normalizedText.replaceAll("([a-z]) (\\d)", "$1$2").toUpperCase();
    }

    /**
     * Normalized address key for anchor matching: lowercased, punctuation
     * stripped, street-suffix noise removed — same shape
     * {@link FileMatchingService#filenameMatchKey} produces for filenames, so
     * an appraisal filename like "5807 Fox Hunt Trl.pdf" and the letter text
     * "5807 FOX HUNT TRAIL" land on the same key.
     */
    public static String addressKey(String value) {
        return FileMatchingService.filenameMatchKey(value);
    }

    /** All distinct, usable order-number tokens for an anchor built from several raw hints. */
    public static Set<String> anchorIdTokens(String... rawHints) {
        Set<String> tokens = new HashSet<>();
        for (String hint : rawHints) {
            if (hint == null || hint.isBlank()) continue;
            String direct = normalizeIdToken(hint);
            // Only accept the whole hint as an ID when it actually looks like one —
            // an address-shaped filename must not become an "order number".
            if (direct != null && ID_TOKEN.matcher(hint.trim()).matches()) {
                tokens.add(direct);
            }
            tokens.addAll(orderNumberTokens(hint));
        }
        return tokens;
    }

    private static String firstGroup(Pattern pattern, String input) {
        Matcher m = pattern.matcher(input);
        return m.find() ? m.group(1) : null;
    }

    private static String clean(String value) {
        if (value == null) return null;
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
