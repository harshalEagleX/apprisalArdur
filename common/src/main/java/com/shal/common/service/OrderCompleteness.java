package com.shal.common.service;

import com.shal.common.entity.FileType;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Single source of truth for what makes an appraisal Order "complete".
 *
 * An order is complete — and only then may QC run, and only then does its document
 * status advance past INCOMPLETE — when it has all REQUIRED document types present
 * and active. Contract is intentionally optional.
 *
 * Every layer that asks "is this order complete / what's missing" MUST route through
 * here: {@code OrderStatusService} (INCOMPLETE vs READY_FOR_QC), the QC completeness
 * gate (order endpoint + batch fan-out), and the frontend document-slots view. Keeping
 * the definition in one place is what prevents an order from showing "Ready for QC"
 * while the QC gate refuses to run it.
 */
public final class OrderCompleteness {

    private OrderCompleteness() {}

    /** Document types an order must have (active) before it is complete / QC-runnable. */
    public static final List<FileType> REQUIRED = List.of(
            FileType.APPRAISAL, FileType.APPRAISAL_XML, FileType.ENGAGEMENT);

    private static final Map<FileType, String> LABELS;
    static {
        Map<FileType, String> m = new LinkedHashMap<>();
        m.put(FileType.APPRAISAL, "Appraisal PDF");
        m.put(FileType.APPRAISAL_XML, "Appraisal XML");
        m.put(FileType.ENGAGEMENT, "Engagement letter");
        LABELS = Map.copyOf(m);
    }

    /** Required types absent from the given present-and-active type set (order preserved). */
    public static List<FileType> missing(Set<FileType> presentActiveTypes) {
        List<FileType> out = new ArrayList<>();
        for (FileType t : REQUIRED) {
            if (presentActiveTypes == null || !presentActiveTypes.contains(t)) out.add(t);
        }
        return out;
    }

    /** Human-readable labels of the missing required documents (empty = complete). */
    public static List<String> missingLabels(Set<FileType> presentActiveTypes) {
        return missing(presentActiveTypes).stream()
                .map(t -> LABELS.getOrDefault(t, t.name()))
                .toList();
    }

    public static boolean isComplete(Set<FileType> presentActiveTypes) {
        return missing(presentActiveTypes).isEmpty();
    }

    public static String label(FileType type) {
        return LABELS.getOrDefault(type, type.name());
    }
}
