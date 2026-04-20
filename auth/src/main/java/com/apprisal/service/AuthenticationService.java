package com.apprisal.service;

import com.apprisal.dto.AuthenticationRequest;
import com.apprisal.dto.AuthenticationResponse;
import com.apprisal.dto.RegisterRequest;
import com.apprisal.entity.User;
import com.apprisal.repository.UserRepository;
import com.apprisal.util.JwtUtils;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import java.util.Objects;

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

        public AuthenticationResponse register(RegisterRequest request) {
                User user = User.builder()
                                .username(request.getUsername())
                                .password(passwordEncoder.encode(request.getPassword()))
                                .role(request.getRole())
                                .build();
                repository.save(Objects.requireNonNull(user));
                UserPrincipal userPrincipal = new UserPrincipal(Objects.requireNonNull(user));
                String jwtToken = jwtUtils.generateToken(userPrincipal);
                return AuthenticationResponse.builder()
                                .token(jwtToken)
                                .build();
        }

        public AuthenticationResponse authenticate(AuthenticationRequest request) {
                authenticationManager.authenticate(
                                new UsernamePasswordAuthenticationToken(
                                                request.getUsername(),
                                                request.getPassword()));
                User user = repository.findByUsername(request.getUsername())
                                .orElseThrow();
                UserPrincipal userPrincipal = new UserPrincipal(Objects.requireNonNull(user));
                String jwtToken = jwtUtils.generateToken(userPrincipal);
                return AuthenticationResponse.builder()
                                .token(jwtToken)
                                .build();
        }
}
