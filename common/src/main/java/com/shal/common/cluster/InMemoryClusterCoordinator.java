package com.shal.common.cluster;

import org.springframework.stereotype.Component;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Default single-node {@link ClusterCoordinator}.
 *
 * Behaviourally identical to the previous in-process cancellation set, so a
 * single-host deployment is unchanged. When the Redis-backed implementation in
 * the app module is also present it is marked {@code @Primary} and wins injection;
 * this bean then simply goes unused (harmless). In a context without Redis (e.g.
 * module-level tests) this is the sole implementation.
 */
@Component
public class InMemoryClusterCoordinator implements ClusterCoordinator {

    private final Set<String> cancels = ConcurrentHashMap.newKeySet();

    @Override
    public void signalCancel(String key) {
        if (key != null) cancels.add(key);
    }

    @Override
    public boolean isCancelSignalled(String key) {
        return key != null && cancels.contains(key);
    }

    @Override
    public void clearCancel(String key) {
        if (key != null) cancels.remove(key);
    }
}
