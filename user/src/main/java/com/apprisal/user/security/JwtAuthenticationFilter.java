package com.apprisal.user.security;

import com.apprisal.user.util.JwtUtils;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.lang.NonNull;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Resolves a JWT from either:
 *   1. HttpOnly "jwt" cookie  (primary path — XSS-safe)
 *   2. Authorization: Bearer … header  (retained for CLI / integration clients)
 *
 * Cookie-first ensures the browser never exposes the token to JavaScript.
 */
@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    public static final String JWT_COOKIE_NAME = "jwt";

    private final JwtUtils jwtUtils;
    private final UserDetailsService userDetailsService;

    public JwtAuthenticationFilter(JwtUtils jwtUtils, UserDetailsService userDetailsService) {
        this.jwtUtils = jwtUtils;
        this.userDetailsService = userDetailsService;
    }

    @Override
    protected void doFilterInternal(
            @NonNull HttpServletRequest request,
            @NonNull HttpServletResponse response,
            @NonNull FilterChain filterChain) throws ServletException, IOException {

        String jwt = extractFromCookie(request);
        if (jwt == null) {
            jwt = extractFromHeader(request);
        }

        if (jwt == null) {
            filterChain.doFilter(request, response);
            return;
        }

        try {
            final String username = jwtUtils.extractUsername(jwt);
            if (username != null && SecurityContextHolder.getContext().getAuthentication() == null) {
                UserDetails userDetails = userDetailsService.loadUserByUsername(username);
                if (jwtUtils.isTokenValid(jwt, userDetails)) {
                    UsernamePasswordAuthenticationToken authToken = new UsernamePasswordAuthenticationToken(
                            userDetails, null, userDetails.getAuthorities());
                    authToken.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
                    SecurityContext context = SecurityContextHolder.createEmptyContext();
                    context.setAuthentication(authToken);
                    SecurityContextHolder.setContext(context);
                }
            }
        } catch (Exception ignored) {
            // Invalid/expired token — let the request proceed unauthenticated;
            // Spring Security will return 401 if the endpoint requires auth.
        }

        filterChain.doFilter(request, response);
    }

    private String extractFromCookie(HttpServletRequest request) {
        Cookie[] cookies = request.getCookies();
        if (cookies == null) return null;
        for (Cookie cookie : cookies) {
            if (JWT_COOKIE_NAME.equals(cookie.getName())) {
                String value = cookie.getValue();
                return (value != null && !value.isBlank()) ? value : null;
            }
        }
        return null;
    }

    private String extractFromHeader(HttpServletRequest request) {
        String header = request.getHeader("Authorization");
        if (header != null && header.startsWith("Bearer ")) {
            String value = header.substring(7);
            return value.isBlank() ? null : value;
        }
        return null;
    }
}
