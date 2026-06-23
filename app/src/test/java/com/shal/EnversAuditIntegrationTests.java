package com.shal;

import com.shal.common.entity.Client;
import com.shal.common.repository.ClientRepository;
import jakarta.persistence.EntityManager;
import org.hibernate.envers.AuditReaderFactory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class EnversAuditIntegrationTests {

    private final ClientRepository clientRepository;
    private final JdbcTemplate jdbcTemplate;
    private final TransactionTemplate transactionTemplate;
    private final EntityManager entityManager;

    @Autowired
    EnversAuditIntegrationTests(ClientRepository clientRepository,
            JdbcTemplate jdbcTemplate,
            TransactionTemplate transactionTemplate,
            EntityManager entityManager) {
        this.clientRepository = clientRepository;
        this.jdbcTemplate = jdbcTemplate;
        this.transactionTemplate = transactionTemplate;
        this.entityManager = entityManager;
    }

    @Test
    void auditedEntityWritesRevisionInfoRows() {
        String code = "AUDIT_TEST_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12).toUpperCase();

        Long clientId = transactionTemplate.execute(status -> {
            Client client = Client.builder()
                    .name("Audit Test Client")
                    .code(code)
                    .status("ACTIVE")
                    .build();
            return clientRepository.saveAndFlush(client).getId();
        });

        transactionTemplate.executeWithoutResult(status -> {
            Client client = clientRepository.findById(clientId).orElseThrow();
            client.setStatus("INACTIVE");
            clientRepository.saveAndFlush(client);
        });

        List<Number> revisions = transactionTemplate.execute(status ->
                AuditReaderFactory.get(entityManager).getRevisions(Client.class, clientId));

        assertThat(revisions).isNotNull();
        assertThat(revisions).hasSizeGreaterThanOrEqualTo(2);

        Integer revisionRows = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM revision_info WHERE id = ?",
                Integer.class,
                revisions.get(0).intValue());
        assertThat(revisionRows).isNotNull();
        assertThat(revisionRows).isPositive();

        transactionTemplate.executeWithoutResult(status ->
                clientRepository.findById(clientId).ifPresent(clientRepository::delete));
    }
}
