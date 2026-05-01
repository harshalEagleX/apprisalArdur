package com.apprisal.config;

import com.apprisal.realtime.QcWebSocketHandler;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final QcWebSocketHandler qcWebSocketHandler;

    @Value("${app.cors.allowed-origins:http://localhost:3000,http://localhost:8080}")
    private String allowedOriginsConfig;

    public WebSocketConfig(QcWebSocketHandler qcWebSocketHandler) {
        this.qcWebSocketHandler = qcWebSocketHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        String[] allowedOrigins = java.util.Arrays.stream(allowedOriginsConfig.split(","))
                .map(String::trim)
                .filter(origin -> !origin.isBlank())
                .toArray(String[]::new);

        registry.addHandler(qcWebSocketHandler, "/ws/qc")
                .setAllowedOrigins(allowedOrigins);
    }
}
