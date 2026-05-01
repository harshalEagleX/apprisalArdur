package com.apprisal.realtime;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.lang.NonNull;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Component
public class QcWebSocketHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(QcWebSocketHandler.class);
    private static final String SUBSCRIBE_PREFIX = "subscribe:";

    private final ObjectMapper objectMapper;
    private final ConcurrentMap<String, Set<WebSocketSession>> topicSessions = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, Set<String>> sessionTopics = new ConcurrentHashMap<>();

    public QcWebSocketHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void handleTextMessage(@NonNull WebSocketSession session, @NonNull TextMessage message) {
        String payload = message.getPayload();
        if (payload == null || !payload.startsWith(SUBSCRIBE_PREFIX)) {
            return;
        }

        String topic = payload.substring(SUBSCRIBE_PREFIX.length()).trim();
        if (!isAllowedTopic(topic)) {
            log.warn("Ignoring invalid websocket topic subscription: {}", topic);
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

    private boolean isAllowedTopic(String topic) {
        return topic.startsWith("/topic/qc/batch/")
                || topic.startsWith("/topic/reviewer/qc/");
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
