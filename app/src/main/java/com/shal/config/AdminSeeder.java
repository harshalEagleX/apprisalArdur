package com.shal.config;

import com.shal.common.entity.Role;
import com.shal.common.entity.User;
import com.shal.common.repository.UserRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.Objects;

@Component
public class AdminSeeder implements CommandLineRunner {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    @Value("${app.admin.username}")
    private String adminEmail;

    @Value("${app.admin.password}")
    private String adminPassword;

    public AdminSeeder(UserRepository userRepository, PasswordEncoder passwordEncoder) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
    }

    @Override
    public void run(String... args) throws Exception {
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
