package com.shal.service;

import com.shal.qc.service.QCProcessingService.QCProgress;
import com.shal.qc.service.QCModelConfig;
import tools.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Durable QC progress store backed by Redis.
 *
 * Replaces the in-memory ConcurrentHashMap in QCProcessingService so that:
 *   - Progress survives JVM restarts (TTL = 6 hours, covers the longest jobs)
 *   - Multiple Java instances share the same progress view
 *   - No memory leak from abandoned progress entries
 *
 * Falls back silently to an in-memory map if Redis is unavailable, preserving
 * the existing single-node behaviour without crashing the QC pipeline.
 */
@Service
public class QCProgressStore {

    private static final Logger log = LoggerFactory.getLogger(QCProgressStore.class);
    private static final String KEY_PREFIX  = "qc:progress:";
    private static final Duration ENTRY_TTL = Duration.ofHours(6);

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;
    /** Fallback in-memory map used when Redis is unavailable. */
    private final ConcurrentHashMap<Long, QCProgress> localFallback = new ConcurrentHashMap<>();
    private volatile boolean redisHealthy = true;

    public QCProgressStore(StringRedisTemplate redis, ObjectMapper mapper) {
        this.redis  = redis;
        this.mapper = mapper;
    }

    public void put(Long batchId, QCProgress progress) {
        if (!redisHealthy) {
            localFallback.put(batchId, progress);
            return;
        }
        try {
            String json = mapper.writeValueAsString(toPayload(batchId, progress));
            redis.opsForValue().set(KEY_PREFIX + batchId, json, ENTRY_TTL);
        } catch (Exception e) {
            log.warn("Redis progress write failed for batch {}: {} — using local fallback", batchId, e.getMessage());
            redisHealthy = false;
            localFallback.put(batchId, progress);
        }
    }

    public Optional<QCProgress> get(Long batchId) {
        if (!redisHealthy) {
            return Optional.ofNullable(localFallback.get(batchId));
        }
        try {
            String json = redis.opsForValue().get(KEY_PREFIX + batchId);
            if (json == null) return Optional.ofNullable(localFallback.get(batchId));
            @SuppressWarnings("unchecked")
            Map<String, Object> m = mapper.readValue(json, Map.class);
            return Optional.of(fromPayload(m));
        } catch (Exception e) {
            log.warn("Redis progress read failed for batch {}: {}", batchId, e.getMessage());
            return Optional.ofNullable(localFallback.get(batchId));
        }
    }

    public void remove(Long batchId) {
        localFallback.remove(batchId);
        try {
            redis.delete(KEY_PREFIX + batchId);
        } catch (Exception e) {
            log.debug("Redis progress delete failed for batch {}: {}", batchId, e.getMessage());
        }
    }

    public void putIfAbsent(Long batchId, QCProgress progress) {
        get(batchId).ifPresentOrElse(existing -> {}, () -> put(batchId, progress));
    }

    // ── Serialisation helpers ──────────────────────────────────────────────────

    private Map<String, Object> toPayload(Long batchId, QCProgress p) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("batchId",       batchId);
        m.put("stage",         p.stage());
        m.put("message",       p.message());
        m.put("current",       p.current());
        m.put("total",         p.total());
        m.put("running",       p.running());
        m.put("modelProvider", p.modelProvider());
        m.put("modelName",     p.modelName());
        m.put("visionModel",   p.visionModel());
        m.put("startedAt",     p.startedAt());
        m.put("updatedAt",     p.updatedAt());
        m.put("subStage",      p.subStage());
        m.put("subMessage",    p.subMessage());
        m.put("subPercent",    p.subPercent());
        m.put("subElapsedMs",  p.subElapsedMs());
        return m;
    }

    private QCProgress fromPayload(Map<String, Object> m) {
        return new QCProgress(
                (String)  m.get("stage"),
                (String)  m.get("message"),
                numberInt(m.get("current")),
                numberInt(m.get("total")),
                Boolean.TRUE.equals(m.get("running")),
                (String)  m.get("modelProvider"),
                (String)  m.get("modelName"),
                (String)  m.get("visionModel"),
                (String)  m.get("startedAt"),
                (String)  m.get("updatedAt"),
                (String)  m.get("subStage"),
                (String)  m.get("subMessage"),
                numberDouble(m.get("subPercent")),
                numberLong(m.get("subElapsedMs"))
        );
    }

    private int    numberInt(Object v)    { return v instanceof Number n ? n.intValue()    : 0;   }
    private long   numberLong(Object v)   { return v instanceof Number n ? n.longValue()   : 0L;  }
    private double numberDouble(Object v) { return v instanceof Number n ? n.doubleValue() : 0.0; }
}
