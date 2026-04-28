package com.apprisal.config;

import com.apprisal.common.entity.Role;
import com.apprisal.common.entity.User;
import com.apprisal.common.repository.UserRepository;
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
            System.out.println("Admin user already exists.");
        }
    }
}
