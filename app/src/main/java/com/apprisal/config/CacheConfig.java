package com.apprisal.config;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

/**
 * Short-TTL in-process cache for read-mostly data (Scaling Phase 3 / QL-3).
 *
 * The admin dashboards (AnalyticsService) each fire ~8–12 aggregate COUNT/AVG queries
 * per load; with 50 concurrent users polling them, those aggregates dominate DB load.
 * A 30s write-TTL cache collapses repeated identical loads into one query set while
 * keeping the data fresh enough for an operations dashboard.
 *
 * TTL is deliberately short so no explicit eviction is needed — entries simply expire.
 * Caches are created on demand by name (caffeine manager default), so any @Cacheable
 * cacheName works without pre-registration.
 */
@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager();
        manager.setCaffeine(Caffeine.newBuilder()
                .expireAfterWrite(Duration.ofSeconds(30))
                .maximumSize(1_000));
        return manager;
    }
}
