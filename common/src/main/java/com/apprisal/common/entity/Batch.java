package com.apprisal.common.entity;

import jakarta.persistence.*;
import org.hibernate.envers.Audited;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * Batch entity representing a collection of appraisal documents.
 */
@Audited
@Entity
@Table(name = "batch")
public class Batch {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "parent_batch_id", nullable = false)
    private String parentBatchId;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "client_id", nullable = false)
    private Client client;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private BatchStatus status = BatchStatus.UPLOADED;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "assigned_reviewer_id")
    private User assignedReviewer;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "created_by", nullable = false)
    private User createdBy;

    @OneToMany(mappedBy = "batch", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<BatchFile> files = new ArrayList<>();

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    public Batch() {
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

    public String getParentBatchId() {
        return parentBatchId;
    }

    public void setParentBatchId(String parentBatchId) {
        this.parentBatchId = parentBatchId;
    }

    public Client getClient() {
        return client;
    }

    public void setClient(Client client) {
        this.client = client;
    }

    public BatchStatus getStatus() {
        return status;
    }

    public void setStatus(BatchStatus status) {
        this.status = status;
    }

    public User getAssignedReviewer() {
        return assignedReviewer;
    }

    public void setAssignedReviewer(User assignedReviewer) {
        this.assignedReviewer = assignedReviewer;
    }

    public User getCreatedBy() {
        return createdBy;
    }

    public void setCreatedBy(User createdBy) {
        this.createdBy = createdBy;
    }

    public List<BatchFile> getFiles() {
        return files;
    }

    public void setFiles(List<BatchFile> files) {
        this.files = files;
    }

    public void addFile(BatchFile file) {
        files.add(file);
        file.setBatch(this);
    }

    public void removeFile(BatchFile file) {
        files.remove(file);
        file.setBatch(null);
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
    public static BatchBuilder builder() {
        return new BatchBuilder();
    }

    public static class BatchBuilder {
        private Long id;
        private String parentBatchId;
        private Client client;
        private BatchStatus status = BatchStatus.UPLOADED;
        private User assignedReviewer;
        private User createdBy;

        public BatchBuilder id(Long id) {
            this.id = id;
            return this;
        }

        public BatchBuilder parentBatchId(String parentBatchId) {
            this.parentBatchId = parentBatchId;
            return this;
        }

        public BatchBuilder client(Client client) {
            this.client = client;
            return this;
        }

        public BatchBuilder status(BatchStatus status) {
            this.status = status;
            return this;
        }

        public BatchBuilder assignedReviewer(User assignedReviewer) {
            this.assignedReviewer = assignedReviewer;
            return this;
        }

        public BatchBuilder createdBy(User createdBy) {
            this.createdBy = createdBy;
            return this;
        }

        public Batch build() {
            Batch batch = new Batch();
            batch.id = this.id;
            batch.parentBatchId = this.parentBatchId;
            batch.client = this.client;
            batch.status = this.status;
            batch.assignedReviewer = this.assignedReviewer;
            batch.createdBy = this.createdBy;
            return batch;
        }
    }
}
