package com.shal.common.exception;

import java.util.List;

/**
 * Thrown when an uploaded ZIP is structurally invalid — an unsupported internal
 * file type, no appraisal PDF, or a MISMO XML that doesn't pair to a PDF.
 *
 * Extends {@link ValidationException} so it routes through the same VALIDATION_FAILED
 * path as other intake validation, but carries the full list of user-fixable issues
 * so the upload UI can show exactly what to correct. The batch is rejected (never
 * processed) until the structure is fixed and re-uploaded.
 */
public class BatchStructureException extends ValidationException {
    private static final long serialVersionUID = 1L;

    private final transient List<String> issues;

    public BatchStructureException(List<String> issues) {
        super("The ZIP can't be accepted until its structure is fixed.");
        this.issues = issues == null ? List.of() : List.copyOf(issues);
    }

    public List<String> getIssues() {
        return issues;
    }
}
