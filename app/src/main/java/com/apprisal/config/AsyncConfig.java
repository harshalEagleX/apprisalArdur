package com.apprisal.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;

/**
 * Async configuration for background QC processing.
 *
 * Sizing rationale:
 *  - OCR jobs run 5-15 min each and are CPU+IO-heavy.
 *  - Core=4 keeps 4 batches permanently warm without idling extra threads.
 *  - Max=10 allows bursting when demand is high.
 *  - Queue=100 absorbs upload bursts without blocking HTTP threads.
 *  - AbortPolicy: when the queue is full, return HTTP 503 to the admin
 *    so they get clear feedback rather than silently blocking the request thread.
 */
@Configuration
@EnableAsync
public class AsyncConfig {

    private static final Logger log = LoggerFactory.getLogger(AsyncConfig.class);

    @Bean("qcTaskExecutor")
    public Executor qcTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(10);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("qc-worker-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(300);  // 5 min — allow long OCR jobs to finish
        executor.initialize();
        log.info("QC task executor configured: core=4, max=10, queue=100, AbortPolicy");
        return executor;
    }
}
