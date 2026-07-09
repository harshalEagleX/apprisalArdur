package com.shal.common.service;

import com.shal.common.entity.AppraisalTransaction;
import com.shal.common.entity.Batch;
import com.shal.common.entity.BatchFile;
import com.shal.common.entity.Client;
import com.shal.common.entity.FileType;
import com.shal.common.entity.OrderDocumentStatus;
import com.shal.common.entity.TransactionStatus;
import com.shal.common.entity.User;
import com.shal.common.repository.AppraisalTransactionRepository;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.util.AppTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Resolves each ingested {@link BatchFile} to a canonical {@link
 * AppraisalTransaction} (the "Order" business entity), so the same
 * real-world order re-uploaded under a differently-named ZIP folder links
 * back to the record that already exists instead of forking a disconnected
 * duplicate.
 *
 * An Order is the cluster FileMatchingService already understands: one
 * appraisal plus its matched engagement/contract/XML — never a single loose
 * document. Only APPRAISAL files can anchor (create) a new Order. Supporting
 * files (ENGAGEMENT/CONTRACT/APPRAISAL_XML) only ever attach to an Order via
 * an identity match (content-hash, orderId, or propertySetName) against an
 * appraisal; a supporting file with no confident match stays unresolved
 * (order = null) rather than spawning its own standalone Order — the existing
 * NEEDS_ASSIGNMENT flow already surfaces it for manual assignment, and {@link
 * com.shal.batch.service.BatchService#manuallyAssignFile} links the order in
 * once an admin assigns it.
 *
 * Identity is resolved in priority order: exact content-hash match (pure
 * re-upload) → orderId string match (same client) → propertySetName match
 * (same client) → else (appraisals only) a new Order is created. Matches are
 * checked both within the batch currently being resolved (via in-memory
 * indices carried in {@link ResolutionContext}, since sibling files in the
 * same pass may not be flushed yet) and across all previously ingested
 * batches (via {@link BatchFileRepository}). Appraisals are always resolved
 * before supporting files within a batch so a supporting file can match a
 * sibling appraisal that was only just created in this same pass.
 */
@Service
public class OrderResolutionService {

    private static final Logger log = LoggerFactory.getLogger(OrderResolutionService.class);

    private final BatchFileRepository batchFileRepository;
    private final AppraisalTransactionRepository appraisalTransactionRepository;
    private final BusinessEventService businessEventService;
    private final OrderStatusService orderStatusService;

    public OrderResolutionService(BatchFileRepository batchFileRepository,
                                   AppraisalTransactionRepository appraisalTransactionRepository,
                                   BusinessEventService businessEventService,
                                   OrderStatusService orderStatusService) {
        this.batchFileRepository = batchFileRepository;
        this.appraisalTransactionRepository = appraisalTransactionRepository;
        this.businessEventService = businessEventService;
        this.orderStatusService = orderStatusService;
    }

    /**
     * Resolves an Order for every file in the batch. Must run after the
     * batch's final propertySetName normalization (single-set ZIPs clear
     * propertySetName to null) so identity resolution sees the same values
     * the rest of the ingestion pipeline uses.
     *
     * <p>{@code identityBySet} carries the AMC/lender order number sniffed from
     * each order group's MISMO appraisal XML (keyed by propertySetName, see
     * {@code BatchService.extractOrderIdentities}). When a file itself carries no
     * {@code orderId}, that sniffed order number is used as its identity key —
     * so a re-upload under a different folder name still links back to the same
     * Order by the number stated inside its XML. May be null/empty (e.g. the
     * backfill path), in which case resolution falls back to the file's own
     * {@code orderId} exactly as before.
     */
    @Transactional
    public void resolveOrdersForBatch(Batch batch, Client client, User actor,
                                      Map<String, DocumentContentSniffer.OrderIdentity> identityBySet) {
        ResolutionContext ctx = new ResolutionContext();
        Map<String, DocumentContentSniffer.OrderIdentity> ids =
                identityBySet != null ? identityBySet : Map.of();

        // Pass 1: appraisals anchor Orders — resolve these first so a supporting
        // file in pass 2 can match a sibling appraisal created earlier in this
        // same batch.
        for (BatchFile file : batch.getFiles()) {
            if (file.getFileType() == FileType.APPRAISAL) {
                resolveOneFile(file, client, actor, batch.getId(), ctx, sniffedOrderNumber(file, ids));
            }
        }
        // Pass 2: supporting files attach to whichever Order they share identity
        // with; a file with no confident match stays order = null.
        for (BatchFile file : batch.getFiles()) {
            if (file.getFileType() != FileType.APPRAISAL) {
                resolveOneFile(file, client, actor, batch.getId(), ctx, sniffedOrderNumber(file, ids));
            }
        }

        // Pass 3 (fallback): a supporting file still unresolved in a batch that
        // anchored exactly ONE order belongs to that order. A single-order ZIP whose
        // engagement letter states a different order number than the appraisal file
        // naming (real AMC behaviour — e.g. the appraisal is "660006860" while the
        // letter cites the lender loan number) must not leave the order INCOMPLETE
        // with an orphaned engagement. Guarded by the single-appraisal condition so
        // it can never merge documents across orders in a multi-order ZIP.
        attachOrphansToSoleOrder(batch.getFiles(), ctx, actor, batch.getId());

        // NOTE: order documentStatus is NOT recomputed here. During intake the Batch + BatchFiles
        // are still a transient graph (persisted by the caller AFTER this method returns), so a
        // findActiveByOrderId read here sees zero documents and would mis-mark complete orders as
        // INCOMPLETE. The caller (BatchService.extractAndValidateZip) recomputes each resolved
        // order once the batch + files are persisted — see recomputeResolvedOrderStatuses().
    }

    /** The XML-sniffed order number for a file's order group, or null when none was sniffed. */
    private static String sniffedOrderNumber(BatchFile file,
                                              Map<String, DocumentContentSniffer.OrderIdentity> identityBySet) {
        String key = file.getPropertySetName() != null && !file.getPropertySetName().isBlank()
                ? file.getPropertySetName() : "__root__";
        DocumentContentSniffer.OrderIdentity identity = identityBySet.get(key);
        return identity != null ? identity.orderNumber() : null;
    }

    /** The file's own orderId when present, else the order number sniffed from its group's XML. */
    private static String effectiveOrderId(BatchFile file, String sniffedOrderNumber) {
        String own = file.getOrderId();
        if (own != null && !own.isBlank()) return own;
        return sniffedOrderNumber != null && !sniffedOrderNumber.isBlank() ? sniffedOrderNumber : null;
    }

    /**
     * One-time, idempotent reconciliation for files ingested before Order
     * resolution existed (BatchFile.order IS NULL). Safe to re-run — files
     * already linked are skipped by the query itself.
     */
    @Transactional
    public BackfillSummary backfillUnresolvedFiles(User actor) {
        List<BatchFile> unresolved = batchFileRepository.findUnresolvedOrderFiles();
        log.info("Order backfill starting: {} unresolved file(s)", unresolved.size());

        ResolutionContext ctx = new ResolutionContext();
        int duplicatesFound = 0;

        // Appraisals first (anchor Orders), then supporting files (attach or stay
        // unresolved) — same reasoning as resolveOrdersForBatch.
        List<BatchFile> appraisalsFirst = unresolved.stream()
                .sorted(Comparator.comparing((BatchFile f) -> f.getFileType() == FileType.APPRAISAL).reversed())
                .toList();
        for (BatchFile file : appraisalsFirst) {
            Client client = file.getBatch().getClient();
            Long batchId = file.getBatch().getId();
            // Backfill has no batch-level XML identity map — resolve on the file's own orderId.
            boolean wasDuplicate = resolveOneFile(file, client, actor, batchId, ctx, null);
            if (wasDuplicate) duplicatesFound++;
        }

        // Same single-appraisal-batch fallback as intake: attach any still-orphaned
        // supporting file to its batch's sole order. We reload the FULL file set of
        // each affected batch (not just the unresolved rows) so the anchoring appraisal
        // is seen even when it was already linked in an earlier run and only the
        // engagement/contract is orphaned — the exact "order stuck INCOMPLETE" case.
        Set<Long> orphanBatchIds = new HashSet<>();
        for (BatchFile f : unresolved) {
            if (f.getOrder() == null && f.getFileType() != FileType.APPRAISAL && f.getBatch() != null) {
                orphanBatchIds.add(f.getBatch().getId());
            }
        }
        for (Long bId : orphanBatchIds) {
            attachOrphansToSoleOrder(batchFileRepository.findByBatchId(bId), ctx, actor, bId);
        }

        Set<AppraisalTransaction> touchedOrders = new HashSet<>();
        for (BatchFile file : unresolved) {
            if (file.getOrder() != null) touchedOrders.add(file.getOrder());
        }
        touchedOrders.forEach(orderStatusService::recompute);

        BackfillSummary summary = new BackfillSummary(
                unresolved.size(), touchedOrders.size(), ctx.newOrdersCreated, duplicatesFound);
        log.info("Order backfill complete: {}", summary);
        businessEventService.record("ORDER_BACKFILL_COMPLETED", actor, "java", "COMPLETED",
                "AppraisalTransaction", null, null, null, null, null,
                Map.of("filesProcessed", summary.filesProcessed(),
                       "ordersTouched", summary.ordersTouched(),
                       "ordersCreated", summary.ordersCreated(),
                       "duplicatesFound", summary.duplicatesFound()));
        return summary;
    }

    /**
     * Fallback linkage for a single-order batch. When exactly one Order was anchored
     * (one appraisal) in the given file set, every supporting file (engagement /
     * contract / XML) still unresolved after identity matching is attached to that
     * Order. This is the structural truth of a one-appraisal ZIP: its documents
     * belong together even when their filenames/stated identifiers disagree. It never
     * fires for a multi-appraisal (multi-order) batch, so it cannot mis-merge orders.
     */
    private void attachOrphansToSoleOrder(java.util.Collection<BatchFile> batchFiles,
                                          ResolutionContext ctx, User actor, Long batchId) {
        AppraisalTransaction sole = null;
        for (BatchFile f : batchFiles) {
            if (f.getFileType() == FileType.APPRAISAL && f.getOrder() != null) {
                if (sole == null) {
                    sole = f.getOrder();
                } else if (!Objects.equals(sole.getId(), f.getOrder().getId())) {
                    return; // more than one order anchored in this batch — not safe to fan out
                }
            }
        }
        if (sole == null) return; // no anchoring appraisal → nothing to attach to

        for (BatchFile file : batchFiles) {
            if (file.getFileType() == FileType.APPRAISAL || file.getOrder() != null) continue;
            file.setOrder(sole);
            supersedeSlotCollision(sole, file, ctx.slotIndex, actor, batchId);
            if (file.getContentHash() != null) ctx.contentHashIndex.putIfAbsent(file.getContentHash(), sole);
            log.info("Batch {} — linked orphan {} '{}' to sole order {} (single-appraisal batch fallback)",
                    batchId, file.getFileType(), file.getFilename(), sole.getTransactionRef());
        }
    }

    /** Resolves and links one file to its Order. Returns true if it was a pure content-hash duplicate. */
    private boolean resolveOneFile(BatchFile file, Client client, User actor, Long batchId,
                                   ResolutionContext ctx, String sniffedOrderNumber) {
        ResolutionResult result = resolveOrderForFile(file, client, ctx, sniffedOrderNumber);
        AppraisalTransaction order = result.order;
        file.setOrder(order);

        if (order == null) {
            // Supporting file with no confident appraisal match — stays unresolved.
            // NEEDS_ASSIGNMENT (set elsewhere) already surfaces this for manual
            // assignment; manuallyAssignFile() links the order in at that point.
            return false;
        }

        if (result.isDuplicateContent) {
            // Exact re-upload of a document that already exists on this order — a
            // no-op for QC purposes. Keep the row for the batch-membership audit
            // trail but mark it inactive immediately so it's never reprocessed.
            file.setSupersededAt(AppTime.now());
            businessEventService.record("BATCH_FILE_DUPLICATE_LINKED", actor, "java", "LINKED",
                    "AppraisalTransaction", order.getId(),
                    batchId, file.getId(), null, null,
                    Map.of("filename", String.valueOf(file.getFilename()),
                           "orderRef", String.valueOf(order.getTransactionRef())));
        } else {
            supersedeSlotCollision(order, file, ctx.slotIndex, actor, batchId);
        }

        if (file.getContentHash() != null) ctx.contentHashIndex.putIfAbsent(file.getContentHash(), order);
        String orderIdKey = effectiveOrderId(file, sniffedOrderNumber);
        if (orderIdKey != null && !orderIdKey.isBlank()) ctx.orderIdIndex.putIfAbsent(orderIdKey, order);
        if (file.getPropertySetName() != null && !file.getPropertySetName().isBlank()) ctx.propertySetIndex.putIfAbsent(file.getPropertySetName(), order);

        return result.isDuplicateContent;
    }

    private ResolutionResult resolveOrderForFile(BatchFile file, Client client, ResolutionContext ctx,
                                                 String sniffedOrderNumber) {
        // 1. Content-hash exact match — pure re-upload of an already-known document.
        if (file.getContentHash() != null) {
            AppraisalTransaction local = ctx.contentHashIndex.get(file.getContentHash());
            if (local != null) return new ResolutionResult(local, true);

            List<BatchFile> hashMatches = batchFileRepository.findByContentHashLinkedToOrder(file.getContentHash());
            if (!hashMatches.isEmpty()) {
                return new ResolutionResult(hashMatches.get(0).getOrder(), true);
            }
        }

        // 2. orderId exact match, scoped to client. The key is the file's own orderId
        //    (FileMatchingService.extractOrderId — falls back to the bare filename stem
        //    when the name has no underscore-suffixed ID), or — when it has none — the
        //    order number sniffed from its group's MISMO XML.
        //    Within the CURRENT batch (in-memory index) a shared orderId always means the
        //    same order — that's how supporting docs sharing an explicit ID link to their
        //    appraisal. ACROSS batches (DB lookup) we only trust an orderId that is a
        //    stable, distinctive identifier (a real order number or address). A bare
        //    filename stem — "EngagementLetter (2)" is exactly as generic as a folder
        //    named "appraisal" — must NOT merge two unrelated orders whose supporting
        //    docs simply happen to share a duplicate-style filename.
        String orderIdKey = effectiveOrderId(file, sniffedOrderNumber);
        if (orderIdKey != null && !orderIdKey.isBlank()) {
            AppraisalTransaction local = ctx.orderIdIndex.get(orderIdKey);
            if (local != null) return new ResolutionResult(local, false);

            if (isDistinctiveIdentity(orderIdKey)) {
                List<BatchFile> orderIdMatches = batchFileRepository.findByOrderIdStringAndClientId(orderIdKey, client.getId());
                if (!orderIdMatches.isEmpty()) {
                    return new ResolutionResult(orderIdMatches.get(0).getOrder(), false);
                }
            }
        }

        // 3. propertySetName match.
        //    Within the CURRENT batch (in-memory index) a shared propertySetName always
        //    means the same order group — this is how an appraisal and its
        //    engagement/contract/XML in the same order folder link together at intake.
        //    ACROSS batches (DB lookup) we only trust a propertySetName that is a stable,
        //    distinctive property identifier (e.g. an address). A bare ordinal folder
        //    label like "1"/"2" is batch-local and must NOT merge two unrelated orders
        //    that happen to reuse folder "1" — those fall through to content-hash/orderId.
        if (file.getPropertySetName() != null && !file.getPropertySetName().isBlank()) {
            AppraisalTransaction local = ctx.propertySetIndex.get(file.getPropertySetName());
            if (local != null) return new ResolutionResult(local, false);

            if (isDistinctiveIdentity(file.getPropertySetName())) {
                List<BatchFile> setMatches = batchFileRepository.findByPropertySetNameAndClientId(file.getPropertySetName(), client.getId());
                if (!setMatches.isEmpty()) {
                    return new ResolutionResult(setMatches.get(0).getOrder(), false);
                }
            }
        }

        // 4. No identity match anywhere.
        if (file.getFileType() == FileType.APPRAISAL) {
            // Appraisals anchor Orders — a genuinely new order.
            AppraisalTransaction created = createNewOrder(file, client, orderIdKey);
            ctx.newOrdersCreated++;
            return new ResolutionResult(created, false);
        }
        // A supporting file with no confident appraisal match must NOT spawn its
        // own standalone Order — an Order is the (appraisal + engagement + contract
        // + XML) cluster, never a single loose document. Leave unresolved.
        return new ResolutionResult(null, false);
    }

    /**
     * True when a raw identity string — a propertySetName folder label, or a filename-
     * derived orderId — is a stable, distinctive identifier safe to dedup Orders on
     * ACROSS batches (an address like "364 S Vine St" or an AMC order number like
     * "ESCA-0019573"). A bare document-type word or filename — "appraisal" (or a typo/
     * variant like "apprisal"), "EngagementLetter (2)" (the generic OS duplicate-file
     * name Windows/Mac give a second upload of the same template), a purely-numeric/
     * ordinal label ("1", "02") — is batch-local and must NEVER be treated as a
     * cross-batch identity: two unrelated batches (or two unrelated documents within
     * one batch) reusing the same generic label/filename must not collapse into one
     * Order, and a supporting document from one order must not silently attach to a
     * different order that happens to reuse the same generic filename.
     *
     * A blocklist of exact spellings is not enough here (a typo of "appraisal" silently
     * bypasses it) — instead this requires the same shape a real address or order number
     * always has: either an ID-shaped token (an AMC/lender order number), or a house/
     * street number carrying at least two digits alongside other words. Two digits is
     * the deliberate floor — it accepts real street numbers ("364", "9512") while
     * rejecting the single digit inside an OS duplicate-file suffix like "(2)"/"(3)",
     * which is exactly what let "EngagementLetter (2).pdf" from one order silently
     * attach to a same-named engagement letter on an unrelated order.
     */
    public static boolean isDistinctiveIdentity(String name) {
        if (name == null) return false;
        String s = name.trim();
        if (s.length() < 3) return false;
        if (!DocumentContentSniffer.orderNumberTokens(s).isEmpty()) return true;
        if (!s.chars().anyMatch(Character::isLetter)) return false;
        String[] tokens = s.split("\\s+");
        boolean hasMultiDigitToken = java.util.Arrays.stream(tokens)
                .anyMatch(t -> t.replaceAll("[^0-9]", "").length() >= 2);
        return tokens.length >= 2 && hasMultiDigitToken;
    }

    private AppraisalTransaction createNewOrder(BatchFile file, Client client, String orderIdKey) {
        String baseKey = orderIdKey != null && !orderIdKey.isBlank()
                ? orderIdKey
                : (file.getPropertySetName() != null && !file.getPropertySetName().isBlank()
                        ? file.getPropertySetName()
                        : "F" + System.nanoTime());
        String clientPrefix = client.getCode() != null && !client.getCode().isBlank()
                ? client.getCode()
                : "CLI" + client.getId();
        String candidateRef = sanitizeRef(clientPrefix + "-" + baseKey);
        String transactionRef = candidateRef;
        int suffix = 2;
        while (appraisalTransactionRepository.findByTransactionRef(transactionRef).isPresent()) {
            transactionRef = candidateRef + "-" + suffix++;
        }

        AppraisalTransaction order = new AppraisalTransaction();
        order.setTransactionRef(transactionRef);
        order.setClient(client);
        order.setStatus(TransactionStatus.RECEIVED);
        order.setDocumentStatus(OrderDocumentStatus.INCOMPLETE);
        order = appraisalTransactionRepository.save(order);
        log.info("Created new Order {} (client={}) for file '{}'", transactionRef, client.getId(), file.getFilename());
        return order;
    }

    private String sanitizeRef(String raw) {
        String cleaned = raw.replaceAll("[^A-Za-z0-9_-]", "-").replaceAll("-{2,}", "-");
        return cleaned.length() > 100 ? cleaned.substring(0, 100) : cleaned;
    }

    /**
     * When a file resolves to an existing order and another active document
     * of the same type already occupies that slot (either from a previous
     * batch, or another file earlier in this same resolution pass), supersede
     * the older one — this is a corrected re-submission, not a duplicate.
     */
    private void supersedeSlotCollision(AppraisalTransaction order, BatchFile file,
                                        Map<String, BatchFile> slotIndex, User actor, Long batchId) {
        String slotKey = order.getId() + ":" + file.getFileType();
        BatchFile localSlotFile = slotIndex.get(slotKey);
        LocalDateTime now = AppTime.now();

        if (localSlotFile != null) {
            if (!Objects.equals(localSlotFile.getContentHash(), file.getContentHash())) {
                localSlotFile.setSupersededAt(now);
                file.setContentVersion(localSlotFile.getContentVersion() + 1);
            }
            slotIndex.put(slotKey, file);
            return;
        }

        List<BatchFile> activeSameType = batchFileRepository.findActiveByOrderIdAndFileType(order.getId(), file.getFileType());
        for (BatchFile existing : activeSameType) {
            if (Objects.equals(existing.getId(), file.getId())) continue;
            if (!Objects.equals(existing.getContentHash(), file.getContentHash())) {
                existing.setSupersededAt(now);
                batchFileRepository.save(existing);
                file.setContentVersion(Math.max(file.getContentVersion(), existing.getContentVersion() + 1));
                businessEventService.record("ORDER_DOCUMENT_SUPERSEDED", actor, "java", "SUPERSEDED",
                        "AppraisalTransaction", order.getId(), batchId, existing.getId(), null, null,
                        Map.of("supersededBy", String.valueOf(file.getFilename()),
                               "fileType", file.getFileType().name()));
            }
        }
        slotIndex.put(slotKey, file);
    }

    /** Per-resolution-pass local indices — avoids re-querying the DB for siblings not yet flushed. */
    private static final class ResolutionContext {
        final Map<String, AppraisalTransaction> contentHashIndex = new HashMap<>();
        final Map<String, AppraisalTransaction> orderIdIndex = new HashMap<>();
        final Map<String, AppraisalTransaction> propertySetIndex = new HashMap<>();
        final Map<String, BatchFile> slotIndex = new HashMap<>();
        int newOrdersCreated = 0;
    }

    private static final class ResolutionResult {
        final AppraisalTransaction order;
        final boolean isDuplicateContent;

        ResolutionResult(AppraisalTransaction order, boolean isDuplicateContent) {
            this.order = order;
            this.isDuplicateContent = isDuplicateContent;
        }
    }

    public record BackfillSummary(int filesProcessed, int ordersTouched, int ordersCreated, int duplicatesFound) {}
}
