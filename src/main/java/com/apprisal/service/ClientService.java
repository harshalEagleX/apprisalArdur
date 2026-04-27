package com.apprisal.service;

import com.apprisal.entity.Client;
import com.apprisal.exception.ResourceNotFoundException;
import com.apprisal.exception.ValidationException;
import com.apprisal.repository.ClientRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.Objects;
import org.springframework.lang.NonNull;

/**
 * Service for managing client organizations.
 */
@Service
public class ClientService {

    private static final Logger log = LoggerFactory.getLogger(ClientService.class);
    private final ClientRepository clientRepository;

    public ClientService(ClientRepository clientRepository) {
        this.clientRepository = clientRepository;
    }

    @Transactional(readOnly = true)
    public Optional<Client> findById(@NonNull Long id) {
        return clientRepository.findById(id);
    }

    @Transactional(readOnly = true)
    public Optional<Client> findByCode(String code) {
        return clientRepository.findByCode(code);
    }

    @Transactional(readOnly = true)
    public List<Client> findAll() {
        return clientRepository.findAll();
    }

    @Transactional
    @SuppressWarnings("null")
    public @NonNull Client create(String name, String code) {
        if (name == null || name.trim().isEmpty()) {
            throw new ValidationException("name", "Client name is required");
        }
        if (code == null || code.trim().isEmpty()) {
            throw new ValidationException("code", "Client code is required");
        }
        if (clientRepository.existsByCode(code.trim().toUpperCase())) {
            throw new ValidationException("code", "Client code already exists: " + code);
        }

        Client client = Client.builder()
                .name(name.trim())
                .code(code.trim().toUpperCase())
                .status("ACTIVE")
                .build();

        log.info("Created client '{}' with code '{}'", name, code);
        return Objects.requireNonNull(clientRepository.save(client));
    }

    @Transactional
    public @NonNull Client update(@NonNull Long id, String name, String status) {

        Client client = clientRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Client", "id", id));

        if (name != null && !name.trim().isEmpty())
            client.setName(name.trim());
        if (status != null)
            client.setStatus(status);

        log.info("Updated client '{}'", client.getName());
        return clientRepository.save(client);
    }

    @Transactional
    public void delete(Long id) {
        if (id == null) {
            throw new ValidationException("id", "Client ID is required");
        }
        Client client = clientRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Client", "id", id));
        log.warn("Deleting client '{}'", client.getName());
        clientRepository.deleteById(id);
    }

    @Transactional(readOnly = true)
    public long count() {
        return clientRepository.count();
    }
}
