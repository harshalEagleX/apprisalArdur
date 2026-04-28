package com.apprisal.batch.service;

import com.apprisal.common.entity.OperatorSession;
import com.apprisal.common.entity.OperatorSession.Status;
import com.apprisal.common.entity.User;
import com.apprisal.common.repository.OperatorSessionRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Tracks operator sessions for analytics: login time, active minutes, files processed.
 * Called by SecurityConfig on login/logout and by QCProcessingService on file completion.
 */
@Service
public class OperatorSessionService {

    private static final Logger log = LoggerFactory.getLogger(OperatorSessionService.class);
    private static final int IDLE_TIMEOUT_MINUTES = 15;

    private final OperatorSessionRepository repo;

    public OperatorSessionService(OperatorSessionRepository repo) { this.repo = repo; }

    @Transactional
    public OperatorSession startSession(User user, String ipAddress, String userAgent) {
        OperatorSession session = OperatorSession.builder()
                .user(user)
                .sessionToken(UUID.randomUUID().toString())
                .ipAddress(ipAddress)
                .userAgent(userAgent)
                .build();
        session = repo.save(session);
        log.info("Session started for user={} session={}", user.getUsername(), session.getSessionToken());
        return session;
    }

    @Transactional
    public void endSession(String sessionToken) {
        repo.findBySessionToken(sessionToken).ifPresent(s -> {
            s.setEndedAt(LocalDateTime.now());
            s.setStatus(Status.ENDED);
            updateActiveMinutes(s);
            repo.save(s);
            log.info("Session ended for user={} minutes={}", s.getUser().getUsername(), s.getActiveMinutes());
        });
    }

    @Transactional
    public void recordActivity(String sessionToken) {
        repo.findBySessionToken(sessionToken).ifPresent(s -> {
            s.setLastActiveAt(LocalDateTime.now());
            s.setStatus(Status.ACTIVE);
            repo.save(s);
        });
    }

    @Transactional
    public void recordFileProcessed(String sessionToken, boolean success) {
        repo.findBySessionToken(sessionToken).ifPresent(s -> {
            if (success) s.setFilesProcessed(s.getFilesProcessed() + 1);
            else         s.setFilesFailed(s.getFilesFailed() + 1);
            s.setLastActiveAt(LocalDateTime.now());
            repo.save(s);
        });
    }

    @Transactional
    public void recordCorrection(String sessionToken) {
        repo.findBySessionToken(sessionToken).ifPresent(s -> {
            s.setCorrectionsMade(s.getCorrectionsMade() + 1);
            repo.save(s);
        });
    }

    @Transactional(readOnly = true)
    public Optional<OperatorSession> findActive(Long userId) {
        return repo.findByUserIdAndStatus(userId, Status.ACTIVE)
                   .stream().findFirst();
    }

    /** Mark sessions idle after IDLE_TIMEOUT_MINUTES of inactivity. Runs every 5 minutes. */
    @Scheduled(fixedDelay = 300_000)
    @Transactional
    public void markIdleSessions() {
        LocalDateTime threshold = LocalDateTime.now().minusMinutes(IDLE_TIMEOUT_MINUTES);
        List<OperatorSession> active = repo.findAll().stream()
                .filter(s -> s.getStatus() == Status.ACTIVE)
                .filter(s -> s.getLastActiveAt() != null && s.getLastActiveAt().isBefore(threshold))
                .toList();
        for (OperatorSession s : active) {
            s.setStatus(Status.IDLE);
            updateActiveMinutes(s);
            repo.save(s);
        }
        if (!active.isEmpty()) log.debug("Marked {} sessions as IDLE", active.size());
    }

    private void updateActiveMinutes(OperatorSession s) {
        if (s.getStartedAt() != null && s.getLastActiveAt() != null) {
            long minutes = ChronoUnit.MINUTES.between(s.getStartedAt(), s.getLastActiveAt());
            s.setActiveMinutes((int) Math.max(0, minutes));
        }
    }
}
