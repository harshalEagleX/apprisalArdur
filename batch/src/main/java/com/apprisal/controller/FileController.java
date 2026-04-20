package com.apprisal.controller;

import com.apprisal.entity.BatchFile;
import com.apprisal.repository.BatchFileRepository;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

import java.io.File;
import org.springframework.lang.NonNull;

/**
 * Controller to serve batch files (PDFs) for viewing.
 */
@Controller
public class FileController {

    private final BatchFileRepository batchFileRepository;

    public FileController(BatchFileRepository batchFileRepository) {
        this.batchFileRepository = batchFileRepository;
    }

    /**
     * Serve a batch file (PDF) for inline viewing in iframe.
     */
    @GetMapping("/files/{batchFileId}")

    public ResponseEntity<Resource> serveFile(@PathVariable @NonNull Long batchFileId) {
        BatchFile batchFile = batchFileRepository.findById(batchFileId).orElse(null);

        if (batchFile == null || batchFile.getStoragePath() == null) {
            return ResponseEntity.notFound().build();
        }

        File file = new File(batchFile.getStoragePath());
        if (!file.exists()) {
            return ResponseEntity.notFound().build();
        }

        FileSystemResource resource = new FileSystemResource(file);

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=\"" + batchFile.getFilename() + "\"")
                .contentType(java.util.Objects.requireNonNull(MediaType.APPLICATION_PDF))
                .body(resource);
    }
}
