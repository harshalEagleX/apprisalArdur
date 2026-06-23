package com.shal.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;

/**
 * Async configuration for background QC processing.
 *
 * Sizing rationale (memory-bound, not CPU-bound):
 *  - Each in-flight document peaks around 400-500MB during OCR (PaddleOCR holds
 *    its model in memory for the duration of extraction).
 *  - On an 8GB box, 2 concurrent documents (~0.8-1GB OCR) fits alongside Spring
 *    Boot (~0.5GB), Postgres connections, and the Next.js process; 3+ risks OOM.
 *    So the pool is a HARD cap of 2 (core == max), not a bursting pool.
 *  - Queue=100 absorbs upload bursts: excess batches wait rather than run
 *    concurrently; AbortPolicy returns HTTP 503 only on extreme overload.
 *  - Configurable (P-4): bump qc.executor.* on a 16GB box (e.g. 4) without code.
 */
@Configuration
@EnableAsync
public class AsyncConfig {

    private static final Logger log = LoggerFactory.getLogger(AsyncConfig.class);

    @Value("${qc.executor.core-pool-size:2}")
    private int corePoolSize;
    @Value("${qc.executor.max-pool-size:2}")
    private int maxPoolSize;
    @Value("${qc.executor.queue-capacity:100}")
    private int queueCapacity;

    @Bean("qcTaskExecutor")
    public Executor qcTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(corePoolSize);
        executor.setMaxPoolSize(maxPoolSize);
        executor.setQueueCapacity(queueCapacity);
        executor.setThreadNamePrefix("qc-worker-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(300);  // 5 min — allow long OCR jobs to finish
        executor.initialize();
        log.info("QC task executor configured: core={}, max={}, queue={}, AbortPolicy",
                corePoolSize, maxPoolSize, queueCapacity);
        return executor;
    }
}
