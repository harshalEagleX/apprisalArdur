package com.shal.realtime;

import com.shal.config.WebSocketAuthHandshakeInterceptor;
import com.shal.common.entity.Role;
import com.shal.common.entity.User;
import com.shal.common.repository.BatchRepository;
import com.shal.common.repository.QCResultRepository;
import com.shal.common.repository.UserRepository;
import com.shal.common.security.UserPrincipal;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.lang.NonNull;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.security.Principal;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Component
public class QcWebSocketHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(QcWebSocketHandler.class);
    private static final String SUBSCRIBE_PREFIX = "subscribe:";
    private static final String ADMIN_NOTIFICATIONS_TOPIC    = "/topic/admin/notifications";
    private static final String REVIEWER_NOTIFICATIONS_TOPIC = "/topic/reviewer/notifications";

    private final ObjectMapper objectMapper;
    private final BatchRepository batchRepository;
    private final QCResultRepository qcResultRepository;
    private final UserRepository userRepository;
    private final ConcurrentMap<String, Set<WebSocketSession>> topicSessions = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, Set<String>> sessionTopics = new ConcurrentHashMap<>();

    public QcWebSocketHandler(ObjectMapper objectMapper,
                              BatchRepository batchRepository,
                              QCResultRepository qcResultRepository,
                              UserRepository userRepository) {
        this.objectMapper = objectMapper;
        this.batchRepository = batchRepository;
        this.qcResultRepository = qcResultRepository;
        this.userRepository = userRepository;
    }

    @Override
    public void handleTextMessage(@NonNull WebSocketSession session, @NonNull TextMessage message) {
        String payload = message.getPayload();
        if (payload == null || !payload.startsWith(SUBSCRIBE_PREFIX)) {
            return;
        }

        String topic = payload.substring(SUBSCRIBE_PREFIX.length()).trim();
        if (!isAuthorizedTopic(session, topic)) {
            log.warn("Ignoring unauthorized websocket topic subscription: session={}, topic={}", session.getId(), topic);
            return;
        }

        topicSessions.computeIfAbsent(topic, ignored -> ConcurrentHashMap.newKeySet()).add(session);
        sessionTopics.computeIfAbsent(session.getId(), ignored -> ConcurrentHashMap.newKeySet()).add(topic);
        log.debug("WebSocket session {} subscribed to {}", session.getId(), topic);
    }

    @Override
    public void afterConnectionClosed(@NonNull WebSocketSession session, @NonNull CloseStatus status) {
        removeSession(session);
    }

    @Override
    public void handleTransportError(@NonNull WebSocketSession session, @NonNull Throwable exception) {
        log.debug("WebSocket transport error for session {}: {}", session.getId(), exception.getMessage());
        removeSession(session);
    }

    public void broadcast(String topic, Object payload) {
        Set<WebSocketSession> sessions = topicSessions.get(topic);
        if (sessions == null || sessions.isEmpty()) {
            return;
        }

        String json;
        try {
            json = objectMapper.writeValueAsString(Map.of("topic", topic, "payload", payload));
        } catch (JacksonException e) {
            log.warn("Failed to serialize websocket payload for {}: {}", topic, e.getMessage());
            return;
        }

        TextMessage message = new TextMessage(json);
        for (WebSocketSession session : sessions) {
            if (!session.isOpen()) {
                removeSession(session);
                continue;
            }
            try {
                synchronized (session) {
                    session.sendMessage(message);
                }
            } catch (IOException e) {
                log.debug("Failed to send websocket message to session {}: {}", session.getId(), e.getMessage());
                removeSession(session);
            }
        }
    }

    private boolean isAuthorizedTopic(WebSocketSession session, String topic) {
        Optional<User> user = currentUser(session);
        if (user.isEmpty()) {
            return false;
        }
        User actor = user.get();
        if (ADMIN_NOTIFICATIONS_TOPIC.equals(topic)) {
            return actor.getRole() == Role.ADMIN;
        }
        if (REVIEWER_NOTIFICATIONS_TOPIC.equals(topic)) {
            return actor.getRole() == Role.REVIEWER || actor.getRole() == Role.ADMIN;
        }
        if (topic.startsWith("/topic/qc/batch/")) {
            Long batchId = parseIdAfter(topic, "/topic/qc/batch/");
            if (batchId == null) {
                return false;
            }
            if (actor.getRole() == Role.ADMIN) {
                return true;
            }
            return batchRepository.isReviewerAssigned(batchId, actor.getId());
        }
        if (topic.startsWith("/topic/reviewer/qc/")) {
            Long qcResultId = parseIdAfter(topic, "/topic/reviewer/qc/");
            if (qcResultId == null) {
                return false;
            }
            return actor.getRole() == Role.ADMIN || qcResultRepository.isReviewerAssigned(qcResultId, actor.getId());
        }
        return false;
    }

    private Optional<User> currentUser(WebSocketSession session) {
        Principal principal = session.getPrincipal();
        Optional<User> principalUser = userFromAuthentication(principal instanceof Authentication authentication ? authentication : null);
        if (principalUser.isPresent()) {
            return principalUser;
        }

        Object handshakeAuth = session.getAttributes().get(WebSocketAuthHandshakeInterceptor.AUTHENTICATION_ATTRIBUTE);
        if (handshakeAuth instanceof Authentication authentication) {
            Optional<User> handshakeUser = userFromAuthentication(authentication);
            if (handshakeUser.isPresent()) {
                return handshakeUser;
            }
        }
        if (principal != null && principal.getName() != null && !principal.getName().isBlank()) {
            return userRepository.findByUsername(principal.getName());
        }
        return Optional.empty();
    }

    private Optional<User> userFromAuthentication(Authentication authentication) {
        if (authentication == null) {
            return Optional.empty();
        }
        Object authPrincipal = authentication.getPrincipal();
        if (authPrincipal instanceof UserPrincipal userPrincipal) {
            return Optional.of(userPrincipal.getUser());
        }
        String name = authentication.getName();
        if (name != null && !name.isBlank()) {
            return userRepository.findByUsername(name);
        }
        return Optional.empty();
    }

    private Long parseIdAfter(String topic, String prefix) {
        try {
            String suffix = topic.substring(prefix.length());
            int slash = suffix.indexOf('/');
            String value = slash >= 0 ? suffix.substring(0, slash) : suffix;
            return Long.parseLong(value);
        } catch (Exception e) {
            return null;
        }
    }

    private void removeSession(WebSocketSession session) {
        Set<String> topics = sessionTopics.remove(session.getId());
        if (topics == null) {
            return;
        }
        for (String topic : topics) {
            Set<WebSocketSession> sessions = topicSessions.get(topic);
            if (sessions != null) {
                sessions.remove(session);
                if (sessions.isEmpty()) {
                    topicSessions.remove(topic);
                }
            }
        }
    }
}
