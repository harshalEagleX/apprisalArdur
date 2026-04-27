package com.apprisal.controller;

import com.apprisal.entity.BatchFile;
import com.apprisal.entity.Role;
import com.apprisal.repository.BatchFileRepository;
import com.apprisal.service.UserPrincipal;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

import java.io.File;
import java.nio.file.Path;
import java.nio.file.Paths;
import org.springframework.lang.NonNull;

/**
 * Controller to serve batch files (PDFs) for viewing.
 * SECURITY: enforces ownership — users can only view files belonging to their client.
 * ADMINs and REVIEWERs can view all files.
 */
@Controller
public class FileController {

    private final BatchFileRepository batchFileRepository;

    public FileController(BatchFileRepository batchFileRepository) {
        this.batchFileRepository = batchFileRepository;
    }

    @GetMapping("/files/{batchFileId}")
    public ResponseEntity<Resource> serveFile(
            @PathVariable @NonNull Long batchFileId,
            @AuthenticationPrincipal UserPrincipal principal) {

        BatchFile batchFile = batchFileRepository.findById(batchFileId).orElse(null);

        if (batchFile == null || batchFile.getStoragePath() == null) {
            return ResponseEntity.notFound().build();
        }

        // SECURITY: ownership check — CLIENT users can only access their own batch files
        if (principal != null) {
            Role role = principal.getUser().getRole();
            if (role == Role.CLIENT) {
                Long userClientId  = principal.getUser().getClient() != null ? principal.getUser().getClient().getId() : null;
                Long fileClientId  = batchFile.getBatch() != null && batchFile.getBatch().getClient() != null
                                   ? batchFile.getBatch().getClient().getId() : null;
                if (userClientId == null || !userClientId.equals(fileClientId)) {
                    return ResponseEntity.status(403).build();
                }
            }
            // ADMINs and REVIEWERs can access all files
        }

        // SECURITY: path traversal guard — ensure resolved path is within the storage directory
        File file = new File(batchFile.getStoragePath());
        try {
            Path canonical = file.toPath().toRealPath();
            // Verify the file is a PDF by checking extension
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
