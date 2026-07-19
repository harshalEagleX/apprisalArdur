package com.shal.user.service;

import com.shal.common.util.AppTime;
import com.shal.common.dto.AuthenticationRequest;
import com.shal.common.dto.RegisterRequest;
import com.shal.common.entity.User;
import com.shal.common.exception.ValidationException;
import com.shal.common.repository.UserRepository;
import com.shal.user.util.JwtUtils;
import com.shal.common.security.UserPrincipal;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import java.util.Objects;

/**
 * Validates credentials and issues a signed JWT.
 * The controller is responsible for placing the token into an HttpOnly cookie —
 * this service is intentionally cookie-unaware.
 */
@Service
public class AuthenticationService {

        private final UserRepository repository;
        private final PasswordEncoder passwordEncoder;
        private final JwtUtils jwtUtils;
        private final AuthenticationManager authenticationManager;

        public AuthenticationService(UserRepository repository,
                        PasswordEncoder passwordEncoder,
                        JwtUtils jwtUtils,
                        AuthenticationManager authenticationManager) {
                this.repository = repository;
                this.passwordEncoder = passwordEncoder;
                this.jwtUtils = jwtUtils;
                this.authenticationManager = authenticationManager;
        }

        public String register(RegisterRequest request) {
                if (request.password() == null || request.password().length() < UserService.PASSWORD_MIN_LENGTH) {
                        throw new ValidationException("password", "Password must be at least " + UserService.PASSWORD_MIN_LENGTH + " characters");
                }
                User user = User.builder()
                                .username(request.username())
                                .password(passwordEncoder.encode(request.password()))
                                .role(request.role())
                                .build();
                repository.save(Objects.requireNonNull(user));
                return jwtUtils.generateToken(new UserPrincipal(Objects.requireNonNull(user)));
        }

        public String authenticate(AuthenticationRequest request) {
                authenticationManager.authenticate(
                                new UsernamePasswordAuthenticationToken(
                                                request.username(),
                                                request.password()));
                User user = repository.findByUsername(request.username()).orElseThrow();
                user.setLastLoginAt(AppTime.now());
                repository.save(Objects.requireNonNull(user));
                return jwtUtils.generateToken(new UserPrincipal(Objects.requireNonNull(user)));
        }
}
