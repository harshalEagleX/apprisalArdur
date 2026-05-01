package com.apprisal.realtime;

import com.apprisal.common.realtime.RealtimeEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class WebSocketRealtimeEventPublisher implements RealtimeEventPublisher {

    private final QcWebSocketHandler webSocketHandler;

    public WebSocketRealtimeEventPublisher(QcWebSocketHandler webSocketHandler) {
        this.webSocketHandler = webSocketHandler;
    }

    @Override
    public void publish(String topic, Object payload) {
        webSocketHandler.broadcast(topic, payload);
    }
}
