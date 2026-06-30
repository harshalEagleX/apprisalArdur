package com.shal.load.data;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/**
 * Generates realistic synthetic test data for load tests.
 *
 * Produces:
 *  - Minimal but valid ZIP files containing one PDF stub + optional manifest.json
 *  - Randomized manifest.json bodies (amc_code, order_number, property_address)
 *  - Auth credential pairs for seeded test users
 *  - Transaction creation request bodies
 */
public final class SyntheticData {

    // Minimal 1-page PDF that passes ZIP extraction (real file magic bytes)
    private static final byte[] MINIMAL_PDF = buildMinimalPdf();

    private static final String[] AMC_CODES = {
        "FIRSTAM", "CORELOGIC", "LANDSAFE", "VEROS", "SOLIDIFI",
        "CLAROCITY", "RELS", "GREENLIGHT", "TITANIUM", "NATISTAR",
        "STREETLINKS", "APPRAISAL1", "AMROCK", "SERVICELINK", "NATIONWIDE"
    };

    private static final String[] STREET_TYPES = {"St", "Ave", "Blvd", "Dr", "Ln", "Way", "Ct", "Rd"};

    private static final String[][] CITY_STATE_ZIP = {
        {"Phoenix", "AZ", "85001"},  {"Houston", "TX", "77001"},
        {"Atlanta", "GA", "30301"},  {"Denver", "CO", "80201"},
        {"Chicago", "IL", "60601"},  {"Seattle", "WA", "98101"},
        {"Miami", "FL", "33101"},    {"Boston", "MA", "02101"},
        {"Dallas", "TX", "75201"},   {"Portland", "OR", "97201"}
    };

    private static final Random RNG = new Random();

    private SyntheticData() {}

    // ── ZIP factories ─────────────────────────────────────────────────────────

    /** Minimal ZIP with one PDF stub — no manifest. */
    public static byte[] minimalZip(String filename) {
        return buildZip(Map.of(filename, MINIMAL_PDF));
    }

    /** ZIP with a PDF stub + manifest.json describing a new transaction. */
    public static byte[] zipWithManifest(String amcCode, String orderNumber, String address) {
        String manifest = buildManifest(amcCode, orderNumber, address, null);
        Map<String, byte[]> entries = new LinkedHashMap<>();
        entries.put("appraisal.pdf", MINIMAL_PDF);
        entries.put("manifest.json", manifest.getBytes(StandardCharsets.UTF_8));
        return buildZip(entries);
    }

    /** ZIP for a revision — is_revision_of points to an existing transactionRef. */
    public static byte[] zipWithRevisionManifest(String amcCode, String orderNumber,
                                                  String address, String revisedFromRef) {
        String manifest = buildManifest(amcCode, orderNumber, address, revisedFromRef);
        Map<String, byte[]> entries = new LinkedHashMap<>();
        entries.put("revision_appraisal.pdf", MINIMAL_PDF);
        entries.put("manifest.json", manifest.getBytes(StandardCharsets.UTF_8));
        return buildZip(entries);
    }

    // ── JSON body builders ────────────────────────────────────────────────────

    public static String authBody(String username, String password) {
        return "{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}";
    }

    public static String createTransactionBody(String amcCode, String orderNumber, String address, Long clientId) {
        return String.format(
            "{\"amcCode\":\"%s\",\"orderNumber\":\"%s\",\"propertyAddress\":\"%s\",\"clientId\":%d}",
            amcCode, orderNumber, address, clientId);
    }

    public static String createUserBody(String username, String role, Long clientId) {
        return String.format(
            "{\"username\":\"%s\",\"password\":\"LoadTest1!\",\"role\":\"%s\"," +
            "\"fullName\":\"Load Test %s\",\"email\":\"%s@loadtest.local\",\"clientId\":%d}",
            username, role, username, username, clientId);
    }

    public static String saveDecisionBody(long ruleResultId, String decision) {
        return String.format(
            "{\"ruleResultId\":%d,\"decision\":\"%s\",\"comment\":\"Load test decision\"}",
            ruleResultId, decision);
    }

    public static String correctionBody(String fieldName, String originalValue, String correctedValue) {
        return String.format(
            "{\"fieldName\":\"%s\",\"originalValue\":\"%s\",\"correctedValue\":\"%s\"," +
            "\"reason\":\"wrong_value\",\"documentId\":\"load-test-doc\"}",
            fieldName, originalValue, correctedValue);
    }

    // ── Randomised data generators ─────────────────────────────────────────────

    public static String randomAmcCode() {
        return AMC_CODES[RNG.nextInt(AMC_CODES.length)];
    }

    public static String randomOrderNumber() {
        return String.format("LN%08d", RNG.nextInt(100_000_000));
    }

    public static String randomAddress() {
        String[] cs = CITY_STATE_ZIP[RNG.nextInt(CITY_STATE_ZIP.length)];
        String street = (100 + RNG.nextInt(9900)) + " "
            + randomWord(6) + " " + STREET_TYPES[RNG.nextInt(STREET_TYPES.length)];
        return street + ", " + cs[0] + ", " + cs[1] + " " + cs[2];
    }

    /** Generate a feeder-style list of N rows for use in Gatling CSV feeders. */
    public static List<Map<String, Object>> generateManifestRows(int count) {
        List<Map<String, Object>> rows = new ArrayList<>(count);
        Set<String> usedRefs = new HashSet<>();
        for (int i = 0; i < count; i++) {
            String amc = randomAmcCode();
            String order = randomOrderNumber();
            String address = randomAddress();
            String ref = "LT-" + amc + "-" + order;
            while (usedRefs.contains(ref)) {
                order = randomOrderNumber();
                ref = "LT-" + amc + "-" + order;
            }
            usedRefs.add(ref);
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("amcCode", amc);
            row.put("orderNumber", order);
            row.put("address", address);
            row.put("transactionRef", ref);
            rows.add(row);
        }
        return rows;
    }

    public static String randomFieldName() {
        String[] fields = {"subject_address", "borrower_name", "appraised_value",
            "effective_date", "contract_price", "gla", "land_area", "year_built"};
        return fields[RNG.nextInt(fields.length)];
    }

    public static String randomValue() {
        return String.valueOf(100_000 + RNG.nextInt(900_000));
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private static String buildManifest(String amcCode, String orderNumber,
                                         String address, String revisedFromRef) {
        StringBuilder sb = new StringBuilder();
        sb.append("{\"transaction_ref\":\"LT-").append(amcCode).append("-").append(orderNumber).append("\"");
        sb.append(",\"amc_code\":\"").append(amcCode).append("\"");
        sb.append(",\"order_number\":\"").append(orderNumber).append("\"");
        sb.append(",\"property_address\":\"").append(address).append("\"");
        if (revisedFromRef != null) {
            sb.append(",\"is_revision_of\":\"").append(revisedFromRef).append("\"");
        }
        sb.append("}");
        return sb.toString();
    }

    private static byte[] buildZip(Map<String, byte[]> entries) {
        try {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            try (ZipOutputStream zos = new ZipOutputStream(baos)) {
                for (Map.Entry<String, byte[]> e : entries.entrySet()) {
                    ZipEntry entry = new ZipEntry(e.getKey());
                    zos.putNextEntry(entry);
                    zos.write(e.getValue());
                    zos.closeEntry();
                }
            }
            return baos.toByteArray();
        } catch (Exception ex) {
            throw new RuntimeException("ZIP build failed", ex);
        }
    }

    /** Minimal 1-page PDF — real magic bytes so the server accepts it as a PDF. */
    private static byte[] buildMinimalPdf() {
        // This is a real, valid minimal 1-page PDF that renders as a blank page
        String pdf = "%PDF-1.4\n"
            + "1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n"
            + "2 0 obj\n<</Type /Pages /Kids [3 0 R] /Count 1>>\nendobj\n"
            + "3 0 obj\n<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>>\nendobj\n"
            + "xref\n0 4\n"
            + "0000000000 65535 f \n"
            + "0000000009 00000 n \n"
            + "0000000058 00000 n \n"
            + "0000000115 00000 n \n"
            + "trailer\n<</Size 4 /Root 1 0 R>>\n"
            + "startxref\n190\n%%EOF";
        return pdf.getBytes(StandardCharsets.US_ASCII);
    }

    private static String randomWord(int maxLen) {
        String alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
        int len = 3 + RNG.nextInt(maxLen - 3);
        StringBuilder sb = new StringBuilder(len);
        for (int i = 0; i < len; i++) {
            sb.append(alphabet.charAt(RNG.nextInt(alphabet.length())));
        }
        return sb.toString();
    }
}
