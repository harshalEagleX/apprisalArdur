package com.apprisal.service;

import com.apprisal.entity.Client;
import com.apprisal.entity.Role;
import com.apprisal.entity.User;
import com.apprisal.exception.ResourceNotFoundException;
import com.apprisal.exception.ValidationException;
import com.apprisal.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.Objects;
import org.springframework.lang.NonNull;

/**
 * Service for managing users - CRUD operations and role management.
 */
@Service
public class UserService {

    private static final Logger log = LoggerFactory.getLogger(UserService.class);

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    public UserService(UserRepository userRepository, PasswordEncoder passwordEncoder) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
    }

    public Optional<User> findById(@NonNull Long id) {
        return userRepository.findById(id);
    }

    public Optional<User> findByUsername(String username) {
        return userRepository.findByUsername(username);
    }

    public List<User> findAll() {
        return userRepository.findAll();
    }

    public Page<User> findAll(@NonNull Pageable pageable) {
        return userRepository.findAll(pageable);
    }

    public List<User> findByRole(Role role) {
        return userRepository.findByRole(role);
    }

    public List<User> findByClientId(Long clientId) {
        return userRepository.findByClientId(clientId);
    }

    @Transactional
    @SuppressWarnings("null")
    public @NonNull User create(String username, String password, Role role, String email, String fullName,
            Client client) {
        // Validation
        if (username == null || username.trim().isEmpty()) {
            throw new ValidationException("username", "Username is required");
        }
        if (password == null || password.length() < 6) {
            throw new ValidationException("password", "Password must be at least 6 characters");
        }
        if (role == null) {
            throw new ValidationException("role", "Role is required");
        }
        if (userRepository.findByUsername(username.trim()).isPresent()) {
            throw new ValidationException("username", "Username already exists: " + username);
        }

        User user = User.builder()
                .username(username.trim())
                .password(passwordEncoder.encode(password))
                .role(role)
                .email(email != null ? email.trim() : null)
                .fullName(fullName != null ? fullName.trim() : null)
                .client(client)
                .build();

        log.info("Created user '{}' with role {}", username, role);
        return Objects.requireNonNull(userRepository.save(user));
    }

    @Transactional
    public @NonNull User update(@NonNull Long id, String email, String fullName, Role role, Client client) {

        User user = userRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("User", "id", id));

        if (email != null)
            user.setEmail(email.trim());
        if (fullName != null)
            user.setFullName(fullName.trim());
        if (role != null)
            user.setRole(role);
        if (client != null)
            user.setClient(client);

        log.info("Updated user '{}'", user.getUsername());
        return userRepository.save(user);
    }

    @Transactional
    public void updatePassword(Long id, String newPassword) {
        if (id == null) {
            throw new ValidationException("id", "User ID is required");
        }
        if (newPassword == null || newPassword.length() < 6) {
            throw new ValidationException("password", "Password must be at least 6 characters");
        }
        User user = userRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("User", "id", id));

        user.setPassword(passwordEncoder.encode(newPassword));
        userRepository.save(user);
        log.info("Updated password for user '{}'", user.getUsername());
    }

    @Transactional
    public void delete(Long id) {
        if (id == null) {
            throw new ValidationException("id", "User ID is required");
        }
        User user = userRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("User", "id", id));
        log.warn("Deleting user '{}'", user.getUsername());
        userRepository.deleteById(id);
    }

    public boolean existsByUsername(String username) {
        return userRepository.findByUsername(username).isPresent();
    }

    public long count() {
        return userRepository.count();
    }

    public long countByRole(Role role) {
        return userRepository.countByRole(role);
    }
}
