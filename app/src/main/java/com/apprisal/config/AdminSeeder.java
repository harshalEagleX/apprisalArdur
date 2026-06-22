package com.apprisal.config;

import com.apprisal.common.entity.Role;
import com.apprisal.common.entity.User;
import com.apprisal.common.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.Objects;

@Component
public class AdminSeeder implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(AdminSeeder.class);

    // Known insecure defaults shipped in application.yml for dev convenience. If any
    // of these is still in effect we warn loudly (SEC-002) — and escalate to ERROR
    // when the active profile looks like production — so a missed env var on a real
    // deployment is impossible to overlook. Non-fatal: never blocks an intentional
    // local/dev run.
    private static final String DEFAULT_ADMIN_PASSWORD = "Admin123!";
    private static final String DEFAULT_JWT_SECRET =
            "404E635266556A586E3272357538782F413F4428472B4B6250645367566B5970";

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    @Value("${app.admin.username}")
    private String adminEmail;

    @Value("${app.admin.password}")
    private String adminPassword;

    @Value("${app.jwt.secret:}")
    private String jwtSecret;

    @Value("${server.session.cookie.secure:false}")
    private boolean cookieSecure;

    @Value("${spring.profiles.active:default}")
    private String activeProfiles;

    public AdminSeeder(UserRepository userRepository, PasswordEncoder passwordEncoder) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
    }

    /** Emit security-hardening warnings for insecure defaults (SEC-002). Never throws. */
    private void warnOnInsecureDefaults() {
        boolean looksProd = activeProfiles != null
                && (activeProfiles.contains("prod") || activeProfiles.contains("production"));
        java.util.List<String> issues = new java.util.ArrayList<>();
        if (DEFAULT_ADMIN_PASSWORD.equals(adminPassword)) {
            issues.add("ADMIN_PASSWORD is the built-in default — set a strong ADMIN_PASSWORD env var.");
        }
        if (DEFAULT_JWT_SECRET.equals(jwtSecret)) {
            issues.add("JWT_SECRET is the built-in default — set a unique JWT_SECRET env var (token forgery risk).");
        }
        if (looksProd && !cookieSecure) {
            issues.add("COOKIE_SECURE=false under a production profile — set COOKIE_SECURE=true behind TLS.");
        }
        for (String issue : issues) {
            if (looksProd) {
                log.error("SECURITY (prod): {}", issue);
            } else {
                log.warn("SECURITY: {}", issue);
            }
        }
    }

    @Override
    public void run(String... args) throws Exception {
        warnOnInsecureDefaults();
        Optional<User> userOptional = userRepository.findByUsername(adminEmail);

        if (userOptional.isEmpty()) {
            User admin = User.builder()
                    .username(adminEmail)
                    .password(passwordEncoder.encode(adminPassword))
                    .role(Role.ADMIN)
                    .build();
            userRepository.save(Objects.requireNonNull(admin));
            System.out.println("Admin user seeded successfully.");
        } else {
            User existing = userOptional.get();
            if (!passwordEncoder.matches(adminPassword, existing.getPassword())) {
                existing.setPassword(passwordEncoder.encode(adminPassword));
                userRepository.save(existing);
                System.out.println("Admin password updated to match ADMIN_PASSWORD env var.");
            } else {
                System.out.println("Admin user already exists.");
            }
        }
    }
}
