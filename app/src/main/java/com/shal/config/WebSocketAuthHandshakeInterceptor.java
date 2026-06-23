package com.shal.config;

import com.shal.user.security.JwtAuthenticationFilter;
import com.shal.user.util.JwtUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

import java.security.Principal;
import java.util.List;
import java.util.Map;

/**
 * Authenticates incoming WebSocket upgrade requests.
 *
 * Resolution order:
 *   1. Existing authenticated Spring Security session principal (form-login path)
 *   2. HttpOnly "jwt" cookie in the Upgrade request headers  (primary API path)
 *
 * The old ?access_token= URL-param strategy has been removed because tokens
 * in query strings are logged by every HTTP proxy, server, and browser history.
 */
@Component
public class WebSocketAuthHandshakeInterceptor implements HandshakeInterceptor {

    public static final String AUTHENTICATION_ATTRIBUTE = "WEBSOCKET_AUTHENTICATION";

    private static final Logger log = LoggerFactory.getLogger(WebSocketAuthHandshakeInterceptor.class);

    private final JwtUtils jwtUtils;
    private final UserDetailsService userDetailsService;

    public WebSocketAuthHandshakeInterceptor(JwtUtils jwtUtils, UserDetailsService userDetailsService) {
        this.jwtUtils = jwtUtils;
        this.userDetailsService = userDetailsService;
    }

    @Override
    public boolean beforeHandshake(ServerHttpRequest request, ServerHttpResponse response,
            WebSocketHandler wsHandler, Map<String, Object> attributes) {

        // 1. Honour an already-authenticated Spring Security session (form-login).
        Authentication existing = authenticatedPrincipal(request.getPrincipal());
        if (existing != null) {
            attributes.put(AUTHENTICATION_ATTRIBUTE, existing);
            return true;
        }

        // 2. Read JWT from the HttpOnly cookie present in the Upgrade headers.
        String token = jwtFromCookieHeader(request);
        if (token == null || token.isBlank()) {
            log.warn("WebSocket handshake rejected — no jwt cookie and no active session");
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return false;
        }

        try {
            String username = jwtUtils.extractUsername(token);
            if (username == null || username.isBlank()) {
                response.setStatusCode(HttpStatus.UNAUTHORIZED);
                return false;
            }
            UserDetails userDetails = userDetailsService.loadUserByUsername(username);
            if (!jwtUtils.isTokenValid(token, userDetails)) {
                response.setStatusCode(HttpStatus.UNAUTHORIZED);
                return false;
            }
            UsernamePasswordAuthenticationToken auth = new UsernamePasswordAuthenticationToken(
                    userDetails, null, userDetails.getAuthorities());
            attributes.put(AUTHENTICATION_ATTRIBUTE, auth);
            return true;
        } catch (Exception e) {
            log.warn("WebSocket handshake rejected — invalid jwt cookie: {}", e.getMessage());
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return false;
        }
    }

    @Override
    public void afterHandshake(ServerHttpRequest request, ServerHttpResponse response,
            WebSocketHandler wsHandler, Exception exception) {
        // No-op.
    }

    private Authentication authenticatedPrincipal(Principal principal) {
        if (principal instanceof Authentication auth
                && auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken)) {
            return auth;
        }
        return null;
    }

    /**
     * Parse the "Cookie" header(s) on the HTTP Upgrade request and return the
     * value of the jwt cookie, or null if it is absent.
     */
    private String jwtFromCookieHeader(ServerHttpRequest request) {
        List<String> cookieHeaders = request.getHeaders().get("Cookie");
        if (cookieHeaders == null) return null;
        for (String header : cookieHeaders) {
            for (String pair : header.split(";")) {
                String trimmed = pair.trim();
                if (trimmed.startsWith(JwtAuthenticationFilter.JWT_COOKIE_NAME + "=")) {
                    String value = trimmed.substring(JwtAuthenticationFilter.JWT_COOKIE_NAME.length() + 1).trim();
                    return value.isBlank() ? null : value;
                }
            }
        }
        return null;
    }
}
