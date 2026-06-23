package com.shal.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/**
 * Authoritative route × role authorization matrix for the /api/** security chain
 * (SecurityConfig.apiSecurityFilterChain) — REGRESSION_AUDIT.md Top-5 risk #1
 * "Permissions & roles", previously "no role-matrix test found". The frontend
 * middleware is only the client-side gate; THIS is the gate that actually enforces.
 *
 * Each probe hits a non-existent sub-path under a security-matched prefix so the
 * test exercises the authorization filter in isolation: the AuthorizationFilter
 * runs before the DispatcherServlet, so a DENIED role gets 403 and an ALLOWED role
 * falls through to 404 (no handler) — no real controller is invoked, no side effects.
 *
 *   403            = authenticated but role not permitted (denied)
 *   401 or 403     = unauthenticated (no valid credentials)
 *   not 401/403    = passed the gate (authorized; here 404, no such handler)
 */
@SpringBootTest
class ApiAuthorizationMatrixTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build();
    }

    private static final RequestPostProcessor ADMIN = user("admin-test").roles("ADMIN");
    private static final RequestPostProcessor REVIEWER = user("reviewer-test").roles("REVIEWER");

    private int status(String path, RequestPostProcessor who) throws Exception {
        return mvc.perform(get(path).with(who)).andReturn().getResponse().getStatus();
    }

    private int statusAnon(String path) throws Exception {
        return mvc.perform(get(path).with(anonymous())).andReturn().getResponse().getStatus();
    }

    // ── /api/auth/** — public ────────────────────────────────────────────────
    @Test
    void authEndpointsArePublic() throws Exception {
        assertThat(statusAnon("/api/auth/__authz_probe")).isNotIn(401, 403);
    }

    // ── /api/admin/** — ADMIN only ───────────────────────────────────────────
    @Test
    void adminApiRequiresAdmin() throws Exception {
        assertThat(statusAnon("/api/admin/__authz_probe")).isIn(401, 403);
        assertThat(status("/api/admin/__authz_probe", REVIEWER)).isEqualTo(403);
        assertThat(status("/api/admin/__authz_probe", ADMIN)).isNotIn(401, 403);
    }

    // ── /api/qc/process/** — ADMIN only (more specific than /api/qc/**) ───────
    @Test
    void qcProcessRequiresAdmin() throws Exception {
        assertThat(status("/api/qc/process/__authz_probe", REVIEWER)).isEqualTo(403);
        assertThat(status("/api/qc/process/__authz_probe", ADMIN)).isNotIn(401, 403);
    }

    // ── /api/graph/** — ADMIN only ───────────────────────────────────────────
    @Test
    void graphApiRequiresAdmin() throws Exception {
        assertThat(status("/api/graph/__authz_probe", REVIEWER)).isEqualTo(403);
        assertThat(status("/api/graph/__authz_probe", ADMIN)).isNotIn(401, 403);
    }

    // ── /api/reviewer/** — ADMIN or REVIEWER ─────────────────────────────────
    @Test
    void reviewerApiAllowsBothRoles() throws Exception {
        assertThat(statusAnon("/api/reviewer/__authz_probe")).isIn(401, 403);
        assertThat(status("/api/reviewer/__authz_probe", REVIEWER)).isNotIn(401, 403);
        assertThat(status("/api/reviewer/__authz_probe", ADMIN)).isNotIn(401, 403);
    }

    // ── /api/qc/** — ADMIN or REVIEWER ───────────────────────────────────────
    @Test
    void qcApiAllowsBothRoles() throws Exception {
        assertThat(statusAnon("/api/qc/__authz_probe")).isIn(401, 403);
        assertThat(status("/api/qc/__authz_probe", REVIEWER)).isNotIn(401, 403);
        assertThat(status("/api/qc/__authz_probe", ADMIN)).isNotIn(401, 403);
    }

    // ── /api/analytics/** — ADMIN or REVIEWER ────────────────────────────────
    @Test
    void analyticsApiAllowsBothRoles() throws Exception {
        assertThat(status("/api/analytics/__authz_probe", REVIEWER)).isNotIn(401, 403);
        assertThat(status("/api/analytics/__authz_probe", ADMIN)).isNotIn(401, 403);
    }

    // ── anyRequest().authenticated() — any logged-in user, anon blocked ───────
    @Test
    void otherApiRequiresAuthentication() throws Exception {
        assertThat(statusAnon("/api/__authz_probe")).isIn(401, 403);
        assertThat(status("/api/__authz_probe", REVIEWER)).isNotIn(401, 403);
    }
}
