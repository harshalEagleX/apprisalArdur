package com.shal.config;

import com.shal.realtime.QcWebSocketHandler;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final QcWebSocketHandler qcWebSocketHandler;
    private final WebSocketAuthHandshakeInterceptor authHandshakeInterceptor;

    // Mirrors the HTTP CORS config: default "*" lets the realtime websocket
    // handshake succeed from any host (localhost, LAN IP). Uses
    // setAllowedOriginPatterns so "*" is permitted. Lock down in production.
    @Value("${app.cors.allowed-origin-patterns:*}")
    private String allowedOriginPatternsConfig;

    public WebSocketConfig(QcWebSocketHandler qcWebSocketHandler,
            WebSocketAuthHandshakeInterceptor authHandshakeInterceptor) {
        this.qcWebSocketHandler = qcWebSocketHandler;
        this.authHandshakeInterceptor = authHandshakeInterceptor;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        String[] allowedOriginPatterns = java.util.Arrays.stream(allowedOriginPatternsConfig.split(","))
                .map(String::trim)
                .filter(origin -> !origin.isBlank())
                .toArray(String[]::new);

        registry.addHandler(qcWebSocketHandler, "/ws/qc")
                .addInterceptors(authHandshakeInterceptor)
                .setAllowedOriginPatterns(allowedOriginPatterns);
    }
}
