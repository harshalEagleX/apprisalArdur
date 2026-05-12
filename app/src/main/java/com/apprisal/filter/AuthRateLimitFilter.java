package com.apprisal.filter;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.annotation.Order;
import org.springframework.lang.NonNull;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

/**
 * IP-based rate limiter that protects authentication endpoints from brute-force
 * attacks. Applies only to /api/auth/**.
 *
 * Algorithm: sliding-window per source IP.
 *   - Window:       60 seconds
 *   - Max attempts: 10 per window
 *   - Block period: 5 minutes after the window is exhausted
 *
 * Runs early in the filter chain (@Order(2), just after CorrelationIdFilter)
 * so it fires before Spring Security processes any credentials.
 */
@Component
@Order(2)
public class AuthRateLimitFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(AuthRateLimitFilter.class);

    private static final String AUTH_PATH_PREFIX = "/api/auth/";
    private static final int    MAX_ATTEMPTS     = 10;
    private static final long   WINDOW_MS        = 60_000L;    // 1 minute sliding window
    private static final long   BLOCK_MS         = 300_000L;   // 5 minutes block after exhaustion
    private static final long   CLEANUP_INTERVAL = 10L;        // minutes between stale-entry cleanup

    /**
     * Per-IP state: [windowStartMs, attemptCount, blockedUntilMs]
     * Using a simple long[] avoids object churn for hot-path IPs.
     */
    private final ConcurrentHashMap<String, long[]> ipState = new ConcurrentHashMap<>();
    private final ScheduledExecutorService cleaner = Executors.newSingleThreadScheduledExecutor(
            r -> { Thread t = new Thread(r, "auth-rate-limit-cleaner"); t.setDaemon(true); return t; }
    );

    @PostConstruct
    void startCleaner() {
        cleaner.scheduleAtFixedRate(this::evictStaleEntries,
                CLEANUP_INTERVAL, CLEANUP_INTERVAL, TimeUnit.MINUTES);
    }

    @PreDestroy
    void stopCleaner() {
        cleaner.shutdownNow();
    }

    @Override
    protected boolean shouldNotFilter(@NonNull HttpServletRequest request) {
        return !request.getRequestURI().startsWith(AUTH_PATH_PREFIX);
    }

    @Override
    protected void doFilterInternal(@NonNull HttpServletRequest request,
                                    @NonNull HttpServletResponse response,
                                    @NonNull FilterChain chain) throws ServletException, IOException {
        String ip = resolveClientIp(request);
        long now = System.currentTimeMillis();

        long[] state = ipState.compute(ip, (k, current) -> {
            if (current == null) {
                return new long[]{now, 1L, 0L};  // [windowStart, count, blockedUntil]
            }
            long windowStart = current[0];
            long count       = current[1];
            long blockedUntil = current[2];

            // Still blocked from a previous exhaustion.
            if (now < blockedUntil) {
                return current;
            }
            // Sliding window expired — start a fresh window.
            if (now - windowStart > WINDOW_MS) {
                return new long[]{now, 1L, 0L};
            }
            // Inside the window — increment.
            count++;
            if (count > MAX_ATTEMPTS) {
                // Exhausted: set block expiry and keep recording attempts.
                return new long[]{windowStart, count, now + BLOCK_MS};
            }
            return new long[]{windowStart, count, 0L};
        });

        long blockedUntil = state[2];
        if (blockedUntil > now) {
            long secondsRemaining = (blockedUntil - now) / 1_000L;
            log.warn("Auth rate-limit triggered for IP {} — blocked for {}s", ip, secondsRemaining);
            response.setStatus(429);
            response.setContentType("application/json;charset=UTF-8");
            response.setHeader("Retry-After", String.valueOf(secondsRemaining));
            response.getWriter().write(
                    "{\"error\":\"TOO_MANY_REQUESTS\","
                    + "\"message\":\"Too many login attempts from your IP. "
                    + "Please try again in " + secondsRemaining + " seconds.\"}");
            return;
        }

        chain.doFilter(request, response);
    }

    private void evictStaleEntries() {
        long evictBefore = System.currentTimeMillis() - BLOCK_MS;
        int removed = 0;
        for (var it = ipState.entrySet().iterator(); it.hasNext(); ) {
            var entry = it.next();
            long[] s = entry.getValue();
            // Remove entries whose window AND block period have both expired.
            if (s[0] < evictBefore && s[2] < evictBefore) {
                it.remove();
                removed++;
            }
        }
        if (removed > 0) {
            log.debug("Auth rate-limit cleanup: evicted {} stale IP entries", removed);
        }
    }

    private String resolveClientIp(HttpServletRequest request) {
        String xff = request.getHeader("X-Forwarded-For");
        if (xff != null && !xff.isBlank()) return xff.split(",")[0].trim();
        String xri = request.getHeader("X-Real-IP");
        if (xri != null && !xri.isBlank()) return xri.trim();
        return request.getRemoteAddr();
    }
}
