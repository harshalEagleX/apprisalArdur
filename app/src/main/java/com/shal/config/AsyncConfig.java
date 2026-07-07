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
 * Sizing rationale (I/O-bound — OCR/QC runs off-process in the Python service):
 *  - This pool's workers only submit each order's file pairs to Python and poll for
 *    results; the heavy OCR/LLM work happens in the OCR service, not this JVM. So the
 *    pool is sized for concurrency, not JVM memory.
 *  - Effective sizing comes from application.yml (qc.executor.*): core=2, max=2,
 *    queue=200 by default — i.e. 2 orders processed concurrently, the rest queued.
 *    The real throughput ceiling is the Python OCR service's parallelism (one
 *    GIL-bound uvicorn process locally) and the shared Groq TPM budget — NOT this
 *    pool. Fanning more orders than Python can parallelise makes each one slower,
 *    not the batch faster; see application.yml (qc.executor) for the full rationale.
 *  - AbortPolicy returns HTTP 503 only on extreme overload (queue full).
 *  - Configurable (P-4): tune qc.executor.* per environment without code changes.
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
