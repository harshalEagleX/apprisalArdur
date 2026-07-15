package com.shal.config;

import com.shal.common.entity.Client;
import com.shal.common.repository.ClientRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * Ensures the default AMC client exists on startup so a freshly recreated DB is
 * immediately usable for QC. The client {@code code} is forwarded to SHALqc as the
 * {@code amc_code}, which selects the compiled rule bundle — it MUST match a
 * profile in {@code shalqc/config/amc_profiles/} (only {@code EQUITYSOLUTIONS}
 * ships today), else SHALqc falls back to the generic {@code _base} catalog and
 * every check degrades to VERIFY.
 *
 * <p>Enforced (default): code={@code EQUITYSOLUTIONS}, name "Equity Solutions".
 * Overridable via {@code app.default-client.code} / {@code app.default-client.name}
 * for a different AMC once its bundle is compiled. Runs after {@link AdminSeeder}.
 * Idempotent and non-fatal: it never overwrites an existing client and never
 * blocks startup.
 */
@Component
@Order(20)
public class ClientSeeder implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(ClientSeeder.class);

    private final ClientRepository clientRepository;

    @Value("${app.default-client.code:EQUITYSOLUTIONS}")
    private String defaultClientCode;

    @Value("${app.default-client.name:Equity Solutions}")
    private String defaultClientName;

    public ClientSeeder(ClientRepository clientRepository) {
        this.clientRepository = clientRepository;
    }

    @Override
    public void run(String... args) {
        String code = defaultClientCode == null ? "" : defaultClientCode.trim().toUpperCase();
        if (code.isEmpty()) {
            log.warn("app.default-client.code is blank — skipping default AMC client seed.");
            return;
        }
        try {
            clientRepository.findByCode(code).ifPresentOrElse(
                existing -> log.info("Default AMC client '{}' already present (id={}).", code, existing.getId()),
                () -> {
                    Client client = clientRepository.save(Client.builder()
                            .name(defaultClientName != null && !defaultClientName.isBlank()
                                    ? defaultClientName.trim() : code)
                            .code(code)
                            .status("ACTIVE")
                            .build());
                    log.info("Seeded default AMC client '{}' ({}) — SHALqc will load its compiled bundle.",
                            client.getName(), client.getCode());
                });
        } catch (Exception e) {
            // Never block startup on the seed (e.g. a race with a concurrent instance).
            log.warn("Default AMC client seed for '{}' failed (non-fatal): {}", code, e.getMessage());
        }
    }
}
