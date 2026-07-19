package com.shal.user.security;

import com.shal.user.util.JwtUtils;
import jakarta.servlet.FilterChain;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

/**
 * The JWT filter — EVERY request passes through this.
 *
 * Two failure directions matter and they are not symmetric:
 *   authenticating when it should not  → an auth bypass
 *   throwing on a malformed token      → a 500 instead of a clean 401, and it
 *                                        happens on unauthenticated traffic, so
 *                                        anyone can trigger it
 * Both are covered here; the class had no tests.
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class JwtAuthenticationFilterTest {

    @Mock JwtUtils jwtUtils;
    @Mock UserDetailsService userDetailsService;
    @Mock FilterChain chain;

    private JwtAuthenticationFilter filter() {
        return new JwtAuthenticationFilter(jwtUtils, userDetailsService);
    }

    private static UserDetails details() {
        return new User("alice", "pw", List.of(new SimpleGrantedAuthority("ROLE_REVIEWER")));
    }

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    private void run(MockHttpServletRequest req) throws Exception {
        filter().doFilter(req, new MockHttpServletResponse(), chain);
    }

    private static boolean authenticated() {
        return SecurityContextHolder.getContext().getAuthentication() != null;
    }

    // ── no credentials ──────────────────────────────────────────────────────

    @Test
    @DisplayName("a request with no token passes through unauthenticated")
    void noTokenPassesThrough() throws Exception {
        run(new MockHttpServletRequest());
        verify(chain).doFilter(any(), any());
        assertThat(authenticated()).isFalse();
        verifyNoInteractions(jwtUtils);
    }

    @Test
    @DisplayName("an empty or blank cookie is treated as NO token")
    void blankCookieIsNoToken() throws Exception {
        MockHttpServletRequest req = new MockHttpServletRequest();
        req.setCookies(new Cookie(JwtAuthenticationFilter.JWT_COOKIE_NAME, "   "));
        run(req);
        assertThat(authenticated()).isFalse();
        verifyNoInteractions(jwtUtils);
    }

    @Test
    @DisplayName("an unrelated cookie is ignored")
    void unrelatedCookieIgnored() throws Exception {
        MockHttpServletRequest req = new MockHttpServletRequest();
        req.setCookies(new Cookie("session_theme", "dark"));
        run(req);
        assertThat(authenticated()).isFalse();
    }

    @Test
    @DisplayName("an Authorization header without the Bearer scheme is ignored")
    void nonBearerHeaderIgnored() throws Exception {
        MockHttpServletRequest req = new MockHttpServletRequest();
        req.addHeader("Authorization", "Basic dXNlcjpwYXNz");
        run(req);
        assertThat(authenticated()).isFalse();
        verifyNoInteractions(jwtUtils);
    }

    @Test
    @DisplayName("a Bearer header with an empty token is treated as NO token")
    void emptyBearerIsNoToken() throws Exception {
        MockHttpServletRequest req = new MockHttpServletRequest();
        req.addHeader("Authorization", "Bearer    ");
        run(req);
        assertThat(authenticated()).isFalse();
        verifyNoInteractions(jwtUtils);
    }

    // ── valid credentials ───────────────────────────────────────────────────

    @Test
    @DisplayName("a valid cookie token authenticates the request")
    void validCookieAuthenticates() throws Exception {
        when(jwtUtils.extractUsername("good-token")).thenReturn("alice");
        when(userDetailsService.loadUserByUsername("alice")).thenReturn(details());
        when(jwtUtils.isTokenValid(eq("good-token"), any())).thenReturn(true);

        MockHttpServletRequest req = new MockHttpServletRequest();
        req.setCookies(new Cookie(JwtAuthenticationFilter.JWT_COOKIE_NAME, "good-token"));
        run(req);

        assertThat(authenticated()).isTrue();
        assertThat(SecurityContextHolder.getContext().getAuthentication().getName()).isEqualTo("alice");
        verify(chain).doFilter(any(), any());
    }

    @Test
    @DisplayName("a valid Bearer token authenticates the request")
    void validBearerAuthenticates() throws Exception {
        when(jwtUtils.extractUsername("good-token")).thenReturn("alice");
        when(userDetailsService.loadUserByUsername("alice")).thenReturn(details());
        when(jwtUtils.isTokenValid(eq("good-token"), any())).thenReturn(true);

        MockHttpServletRequest req = new MockHttpServletRequest();
        req.addHeader("Authorization", "Bearer good-token");
        run(req);
        assertThat(authenticated()).isTrue();
    }

    @Test
    @DisplayName("the cookie WINS over the header when both are present")
    void cookiePreferredOverHeader() throws Exception {
        when(jwtUtils.extractUsername("cookie-token")).thenReturn("alice");
        when(userDetailsService.loadUserByUsername("alice")).thenReturn(details());
        when(jwtUtils.isTokenValid(eq("cookie-token"), any())).thenReturn(true);

        MockHttpServletRequest req = new MockHttpServletRequest();
        req.setCookies(new Cookie(JwtAuthenticationFilter.JWT_COOKIE_NAME, "cookie-token"));
        req.addHeader("Authorization", "Bearer header-token");
        run(req);

        assertThat(authenticated()).isTrue();
        verify(jwtUtils).extractUsername("cookie-token");
        verify(jwtUtils, never()).extractUsername("header-token");
    }

    // ── rejection paths (must NOT authenticate, must NOT throw) ─────────────

    @Test
    @DisplayName("a token the validator rejects does NOT authenticate")
    void invalidTokenDoesNotAuthenticate() throws Exception {
        when(jwtUtils.extractUsername("bad-token")).thenReturn("alice");
        when(userDetailsService.loadUserByUsername("alice")).thenReturn(details());
        when(jwtUtils.isTokenValid(eq("bad-token"), any())).thenReturn(false);

        MockHttpServletRequest req = new MockHttpServletRequest();
        req.addHeader("Authorization", "Bearer bad-token");
        run(req);

        assertThat(authenticated()).isFalse();
        verify(chain).doFilter(any(), any());   // request still proceeds → 401 downstream
    }

    @Test
    @DisplayName("a malformed/expired token yields a clean pass-through, never a 500")
    void malformedTokenIsSwallowed() throws Exception {
        // This runs on UNAUTHENTICATED traffic, so anyone could trigger it —
        // an exception escaping here is a 500 that any client can cause at will.
        when(jwtUtils.extractUsername(anyString()))
                .thenThrow(new IllegalArgumentException("malformed JWT"));

        MockHttpServletRequest req = new MockHttpServletRequest();
        req.addHeader("Authorization", "Bearer garbage");
        run(req);

        assertThat(authenticated()).isFalse();
        verify(chain).doFilter(any(), any());
    }

    @Test
    @DisplayName("an unknown user in a well-formed token does not authenticate")
    void unknownUserDoesNotAuthenticate() throws Exception {
        when(jwtUtils.extractUsername("token")).thenReturn("ghost");
        when(userDetailsService.loadUserByUsername("ghost"))
                .thenThrow(new org.springframework.security.core.userdetails
                        .UsernameNotFoundException("no such user"));

        MockHttpServletRequest req = new MockHttpServletRequest();
        req.addHeader("Authorization", "Bearer token");
        run(req);

        assertThat(authenticated()).isFalse();
        verify(chain).doFilter(any(), any());
    }

    @Test
    @DisplayName("an already-authenticated context is left alone")
    void existingAuthenticationNotOverwritten() throws Exception {
        var existing = new org.springframework.security.authentication
                .UsernamePasswordAuthenticationToken("bob", null, List.of());
        SecurityContextHolder.getContext().setAuthentication(existing);
        when(jwtUtils.extractUsername("token")).thenReturn("alice");

        MockHttpServletRequest req = new MockHttpServletRequest();
        req.addHeader("Authorization", "Bearer token");
        run(req);

        // must not silently swap the principal mid-request
        assertThat(SecurityContextHolder.getContext().getAuthentication().getName()).isEqualTo("bob");
        verify(userDetailsService, never()).loadUserByUsername(anyString());
    }

    @Test
    @DisplayName("the chain is ALWAYS continued, on every path")
    void chainAlwaysContinues() throws Exception {
        when(jwtUtils.extractUsername(anyString())).thenThrow(new RuntimeException("boom"));
        MockHttpServletRequest req = new MockHttpServletRequest();
        req.addHeader("Authorization", "Bearer x");
        run(req);
        // a filter that swallows the chain hangs the request
        verify(chain).doFilter(any(), any());
    }
}
