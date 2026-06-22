package com.apprisal.cluster;

import com.apprisal.common.cluster.ClusterCoordinator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Redis-backed {@link ClusterCoordinator} so an admin "Stop QC" reaches a worker
 * running on a different Java instance.
 *
 * Marked {@link Primary} so it is injected ahead of the in-memory default. Mirrors
 * {@code QCProgressStore}'s resilience contract: every Redis op is wrapped and a
 * failure silently falls back to a local in-memory set, so the QC pipeline behaves
 * exactly like the single-node implementation when Redis is down — graceful
 * degradation (P-6), never a crash.
 *
 * Cancel signals carry a TTL (covers the longest job) so a missed clear can never
 * leak a stale "cancel everything" flag.
 */
@Primary
@Component
public class RedisClusterCoordinator implements ClusterCoordinator {

    private static final Logger log = LoggerFactory.getLogger(RedisClusterCoordinator.class);
    private static final String KEY_PREFIX = "qc:cancel:";
    private static final Duration TTL = Duration.ofHours(6);

    private final StringRedisTemplate redis;
    /** Fallback used whenever Redis is unreachable — preserves single-node behaviour. */
    private final Set<Long> localFallback = ConcurrentHashMap.newKeySet();
    private volatile boolean redisHealthy = true;

    public RedisClusterCoordinator(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static String key(Long batchId) {
        return KEY_PREFIX + batchId;
    }

    @Override
    public void signalCancel(Long batchId) {
        if (batchId == null) return;
        localFallback.add(batchId); // always keep the local node responsive immediately
        if (!redisHealthy) return;
        try {
            redis.opsForValue().set(key(batchId), "1", TTL);
        } catch (Exception e) {
            log.warn("Redis cancel-signal write failed for batch {}: {} — using local fallback",
                    batchId, e.getMessage());
            redisHealthy = false;
        }
    }

    @Override
    public boolean isCancelSignalled(Long batchId) {
        if (batchId == null) return false;
        if (localFallback.contains(batchId)) return true; // fast path / fallback
        if (!redisHealthy) return false;
        try {
            return Boolean.TRUE.equals(redis.hasKey(key(batchId)));
        } catch (Exception e) {
            log.warn("Redis cancel-signal read failed for batch {}: {} — using local fallback",
                    batchId, e.getMessage());
            redisHealthy = false;
            return false;
        }
    }

    @Override
    public void clearCancel(Long batchId) {
        if (batchId == null) return;
        localFallback.remove(batchId);
        if (!redisHealthy) return;
        try {
            redis.delete(key(batchId));
        } catch (Exception e) {
            log.warn("Redis cancel-signal clear failed for batch {}: {}", batchId, e.getMessage());
            redisHealthy = false;
        }
    }
}
