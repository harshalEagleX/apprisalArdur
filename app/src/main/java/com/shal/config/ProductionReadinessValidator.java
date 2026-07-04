package com.shal.config;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * Fails the application startup when it is configured to run in production while
 * still carrying the insecure defaults shipped for local dev.
 *
 * The defaults in {@code application.yml} (DB password, admin password, JWT secret)
 * exist so a laptop run "just works" — but shipping them to a real deployment is a
 * token-forgery / account-takeover risk. This guard turns that from a silent hazard
 * into a hard, early failure with an actionable message.
 *
 * Enforcement is on ONLY when the deployment says it is production:
 *   - an active Spring profile contains "prod"/"production", OR
 *   - {@code APP_DEPLOY_STRICT=true} (app.deploy.strict).
 * In plain local/dev runs it degrades to a one-time warning, so nothing local breaks.
 *
 * This is intentionally about *configuration*, not connectivity — a missing DB or a
 * down OCR service is handled by graceful degradation + the preflight script, never
 * by refusing to boot.
 */
@Component
public class ProductionReadinessValidator {

    private static final Logger log = LoggerFactory.getLogger(ProductionReadinessValidator.class);

    // The exact insecure defaults from application.yml — must stay in sync.
    private static final String DEFAULT_DB_PASSWORD = "12345678";
    private static final String DEFAULT_ADMIN_PASSWORD = "Admin123!";
    private static final String DEFAULT_JWT_SECRET =
            "404E635266556A586E3272357538782F413F4428472B4B6250645367566B5970";

    @Value("${spring.datasource.password:}")
    private String dbPassword;

    @Value("${app.admin.password:}")
    private String adminPassword;

    @Value("${app.jwt.secret:}")
    private String jwtSecret;

    @Value("${ocr.service.api-key:}")
    private String internalApiKey;

    @Value("${server.session.cookie.secure:false}")
    private boolean cookieSecure;

    @Value("${spring.profiles.active:default}")
    private String activeProfiles;

    @Value("${app.deploy.strict:false}")
    private boolean strict;

    @PostConstruct
    public void validate() {
        boolean looksProd = activeProfiles != null
                && (activeProfiles.contains("prod") || activeProfiles.contains("production"));
        boolean enforce = strict || looksProd;

        List<String> problems = new ArrayList<>();
        if (DEFAULT_JWT_SECRET.equals(jwtSecret)) {
            problems.add("JWT_SECRET is the built-in default — set a unique JWT_SECRET (token-forgery risk).");
        }
        if (DEFAULT_DB_PASSWORD.equals(dbPassword)) {
            problems.add("DB_PASSWORD is the built-in default — set a real DB_PASSWORD.");
        }
        if (DEFAULT_ADMIN_PASSWORD.equals(adminPassword)) {
            problems.add("ADMIN_PASSWORD is the built-in default — set a strong ADMIN_PASSWORD.");
        }
        if (internalApiKey == null || internalApiKey.isBlank()) {
            problems.add("INTERNAL_API_KEY is not set — the Java↔Python channel would be unauthenticated.");
        }
        if (!cookieSecure) {
            problems.add("COOKIE_SECURE=false — set COOKIE_SECURE=true when serving over HTTPS.");
        }

        if (problems.isEmpty()) {
            log.info("Production-readiness check passed (enforce={}).", enforce);
            return;
        }

        String joined = "\n  - " + String.join("\n  - ", problems);
        if (enforce) {
            throw new IllegalStateException(
                    "Refusing to start: insecure/incomplete production configuration."
                    + joined
                    + "\nSet these via environment variables (see DEPLOYMENT.md), or run without a prod "
                    + "profile / APP_DEPLOY_STRICT for local dev.");
        }
        log.warn("SECURITY — not production-ready (dev run, not enforced):{}", joined);
    }
}
