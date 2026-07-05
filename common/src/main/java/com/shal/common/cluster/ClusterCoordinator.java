package com.shal.common.cluster;

/**
 * Cross-node coordination signals for QC processing.
 *
 * Scope: this exists ONLY to make cancellation work when more than one Java
 * instance runs. Batch *claiming* is already multi-instance-safe at the database
 * level (BatchRepository.markQcProcessingIfTriggerable is a conditional UPDATE —
 * only one node's UPDATE wins). The gap a single in-process map leaves is that an
 * admin "Stop QC" on node A cannot interrupt a worker running on node B.
 *
 * Implementations are best-effort: a failure never throws into the QC pipeline.
 * The default {@link InMemoryClusterCoordinator} preserves today's single-node
 * behaviour exactly; a Redis-backed implementation makes the signal cluster-wide.
 */
public interface ClusterCoordinator {

    /**
     * Broadcast that a QC job should be cancelled, visible to every node. Best-effort.
     *
     * {@code key} is a namespaced job identifier — {@code "batch:" + id} or
     * {@code "order:" + id}. Batch and Order ids are both {@code Long} counting from 1,
     * so the namespace prefix is what stops a batch cancel from also cancelling the
     * same-numbered order (and vice-versa) on the shared Redis keyspace.
     */
    void signalCancel(String key);

    /** True if a cancel was broadcast for this job key by ANY node. Returns false on any error. */
    boolean isCancelSignalled(String key);

    /** Clear the cancel signal once the job has ended. Best-effort. */
    void clearCancel(String key);
}
