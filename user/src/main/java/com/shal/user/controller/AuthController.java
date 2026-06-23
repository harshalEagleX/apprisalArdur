package com.shal.user.controller;

import com.shal.common.dto.AuthenticationRequest;
import com.shal.common.dto.RegisterRequest;
import com.shal.user.security.JwtAuthenticationFilter;
import com.shal.user.service.AuthenticationService;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * Handles token-based authentication.
 *
 * On success, the JWT is written as an HttpOnly, SameSite=Strict cookie so
 * that JavaScript never touches the token (XSS-safe). The response body
 * intentionally does NOT include the token — callers rely on the cookie.
 */
@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private static final long COOKIE_MAX_AGE_SECONDS = 86_400L; // 24 h — matches JwtUtils expiry

    private final AuthenticationService service;

    @Value("${cookie.secure:false}")
    private boolean cookieSecure;

    public AuthController(AuthenticationService service) {
        this.service = service;
    }

    @PostMapping("/register")
    public ResponseEntity<Map<String, String>> register(
            @RequestBody RegisterRequest request,
            HttpServletResponse httpResponse) {
        String token = service.register(request);
        setJwtCookie(httpResponse, token);
        return ResponseEntity.ok(Map.of("status", "ok"));
    }

    @PostMapping("/authenticate")
    public ResponseEntity<Map<String, String>> authenticate(
            @RequestBody AuthenticationRequest request,
            HttpServletResponse httpResponse) {
        String token = service.authenticate(request);
        setJwtCookie(httpResponse, token);
        return ResponseEntity.ok(Map.of("status", "ok"));
    }

    @PostMapping("/logout")
    public ResponseEntity<Map<String, String>> logout(HttpServletResponse httpResponse) {
        clearJwtCookie(httpResponse);
        return ResponseEntity.ok(Map.of("status", "ok"));
    }

    private void setJwtCookie(HttpServletResponse response, String token) {
        ResponseCookie cookie = ResponseCookie.from(JwtAuthenticationFilter.JWT_COOKIE_NAME, token)
                .httpOnly(true)
                .secure(cookieSecure)
                .sameSite("Strict")
                .path("/")
                .maxAge(COOKIE_MAX_AGE_SECONDS)
                .build();
        response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
    }

    private void clearJwtCookie(HttpServletResponse response) {
        ResponseCookie expiredCookie = ResponseCookie.from(JwtAuthenticationFilter.JWT_COOKIE_NAME, "")
                .httpOnly(true)
                .secure(cookieSecure)
                .sameSite("Strict")
                .path("/")
                .maxAge(0)
                .build();
        response.addHeader(HttpHeaders.SET_COOKIE, expiredCookie.toString());
    }
}
