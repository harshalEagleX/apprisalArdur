package com.apprisal.batch.controller;

import com.apprisal.common.entity.BatchFile;
import com.apprisal.common.entity.Role;
import com.apprisal.common.repository.BatchFileRepository;
import com.apprisal.common.security.UserPrincipal;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Controller;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

import java.io.File;
import java.nio.file.Path;
import org.springframework.lang.NonNull;

/**
 * Serves batch PDFs for the reviewer iframe.
 *
 * Ownership rules (two-role model):
 *   ADMIN    — can view any file in the system
 *   REVIEWER — can only view files belonging to batches assigned to them
 */
@Controller
public class FileController {

    private final BatchFileRepository batchFileRepository;

    public FileController(BatchFileRepository batchFileRepository) {
        this.batchFileRepository = batchFileRepository;
    }

    @GetMapping("/files/{batchFileId}")
    @Transactional(readOnly = true)
    public ResponseEntity<Resource> serveFile(
            @PathVariable @NonNull Long batchFileId,
            @AuthenticationPrincipal UserPrincipal principal) {

        BatchFile batchFile = batchFileRepository.findWithBatchAndReviewerById(batchFileId).orElse(null);

        if (batchFile == null || batchFile.getStoragePath() == null) {
            return ResponseEntity.notFound().build();
        }

        // SECURITY: ownership check for REVIEWERs
        if (principal != null && principal.getUser().getRole() == Role.REVIEWER) {
            var batch = batchFile.getBatch();
            var assignedReviewer = batch != null ? batch.getAssignedReviewer() : null;
            if (assignedReviewer == null || !assignedReviewer.getId().equals(principal.getUser().getId())) {
                return ResponseEntity.status(403).build();
            }
        }

        // SECURITY: path traversal guard — ensure the file is a PDF
        File file = new File(batchFile.getStoragePath());
        try {
            Path canonical = file.toPath().toRealPath();
            if (!canonical.toString().toLowerCase().endsWith(".pdf")) {
                return ResponseEntity.status(400).build();
            }
        } catch (Exception e) {
            return ResponseEntity.notFound().build();
        }

        if (!file.exists() || !file.isFile()) {
            return ResponseEntity.notFound().build();
        }

        FileSystemResource resource = new FileSystemResource(file);

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=\"" + batchFile.getFilename() + "\"")
                .header("X-Content-Type-Options", "nosniff")
                .contentType(java.util.Objects.requireNonNull(MediaType.APPLICATION_PDF))
                .body(resource);
    }
}
