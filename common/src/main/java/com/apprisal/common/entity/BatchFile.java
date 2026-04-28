package com.apprisal.common.entity;

import jakarta.persistence.*;
import org.hibernate.envers.Audited;
import java.time.LocalDateTime;

/**
 * BatchFile entity representing individual files within a batch.
 */
@Audited
@Entity
@Table(name = "batch_file")
public class BatchFile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "batch_id", nullable = false)
    private Batch batch;

    @Enumerated(EnumType.STRING)
    @Column(name = "file_type", nullable = false)
    private FileType fileType;

    @Column(nullable = false)
    private String filename;

    @Column(name = "original_path")
    private String originalPath;

    @Column(name = "storage_path")
    private String storagePath;

    @Column(name = "file_size")
    private Long fileSize;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private FileStatus status = FileStatus.PENDING;

    @Column(name = "ocr_data", columnDefinition = "TEXT")
    private String ocrData;

    @Column(name = "error_message")
    private String errorMessage;

    /**
     * Order ID extracted from filename for matching appraisal↔engagement files.
     * Example: appraisal_001.pdf → orderId = "001"
     */
    @Column(name = "order_id")
    private String orderId;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    public BatchFile() {
    }

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    // Getters and Setters
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public Batch getBatch() {
        return batch;
    }

    public void setBatch(Batch batch) {
        this.batch = batch;
    }

    public FileType getFileType() {
        return fileType;
    }

    public void setFileType(FileType fileType) {
        this.fileType = fileType;
    }

    public String getFilename() {
        return filename;
    }

    public void setFilename(String filename) {
        this.filename = filename;
    }

    public String getOriginalPath() {
        return originalPath;
    }

    public void setOriginalPath(String originalPath) {
        this.originalPath = originalPath;
    }

    public String getStoragePath() {
        return storagePath;
    }

    public void setStoragePath(String storagePath) {
        this.storagePath = storagePath;
    }

    public Long getFileSize() {
        return fileSize;
    }

    public void setFileSize(Long fileSize) {
        this.fileSize = fileSize;
    }

    public FileStatus getStatus() {
        return status;
    }

    public void setStatus(FileStatus status) {
        this.status = status;
    }

    public String getOcrData() {
        return ocrData;
    }

    public void setOcrData(String ocrData) {
        this.ocrData = ocrData;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(LocalDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }

    // Builder pattern
    public static BatchFileBuilder builder() {
        return new BatchFileBuilder();
    }

    public static class BatchFileBuilder {
        private Long id;
        private Batch batch;
        private FileType fileType;
        private String filename;
        private String originalPath;
        private String storagePath;
        private Long fileSize;
        private FileStatus status = FileStatus.PENDING;
        private String orderId;

        public BatchFileBuilder id(Long id) {
            this.id = id;
            return this;
        }

        public BatchFileBuilder batch(Batch batch) {
            this.batch = batch;
            return this;
        }

        public BatchFileBuilder fileType(FileType fileType) {
            this.fileType = fileType;
            return this;
        }

        public BatchFileBuilder filename(String filename) {
            this.filename = filename;
            return this;
        }

        public BatchFileBuilder originalPath(String originalPath) {
            this.originalPath = originalPath;
            return this;
        }

        public BatchFileBuilder storagePath(String storagePath) {
            this.storagePath = storagePath;
            return this;
        }

        public BatchFileBuilder fileSize(Long fileSize) {
            this.fileSize = fileSize;
            return this;
        }

        public BatchFileBuilder status(FileStatus status) {
            this.status = status;
            return this;
        }

        public BatchFileBuilder orderId(String orderId) {
            this.orderId = orderId;
            return this;
        }

        public BatchFile build() {
            BatchFile file = new BatchFile();
            file.id = this.id;
            file.batch = this.batch;
            file.fileType = this.fileType;
            file.filename = this.filename;
            file.originalPath = this.originalPath;
            file.storagePath = this.storagePath;
            file.fileSize = this.fileSize;
            file.status = this.status;
            file.orderId = this.orderId;
            return file;
        }
    }
}
