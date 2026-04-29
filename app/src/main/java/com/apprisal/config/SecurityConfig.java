package com.apprisal.config;

import com.apprisal.common.entity.User;
import com.apprisal.user.security.JwtAuthenticationFilter;
import com.apprisal.common.service.AuditLogService;
import com.apprisal.common.security.UserPrincipal;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthFilter;
    private final UserDetailsService userDetailsService;
    private final AuditLogService auditLogService;

    @Value("${app.cors.allowed-origins:http://localhost:3000,http://localhost:8080}")
    private String allowedOriginsConfig;

    public SecurityConfig(JwtAuthenticationFilter jwtAuthFilter,
            UserDetailsService userDetailsService,
            AuditLogService auditLogService) {
        this.jwtAuthFilter = jwtAuthFilter;
        this.userDetailsService = userDetailsService;
        this.auditLogService = auditLogService;
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cfg = new CorsConfiguration();
        // Allow Next.js frontend and any configured production origins
        List<String> origins = List.of(allowedOriginsConfig.split(","));
        cfg.setAllowedOrigins(origins.stream().map(String::trim).toList());
        cfg.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"));
        cfg.setAllowedHeaders(List.of("*"));
        cfg.setExposedHeaders(List.of("X-Correlation-ID", "Set-Cookie"));
        cfg.setAllowCredentials(true);   // required for session cookies (credentials: "include")
        cfg.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cfg);
        return source;
    }

    /**
     * Security filter chain for REST API endpoints
     * Supports both JWT authentication (for mobile/external) and session-based auth
     * (for web AJAX calls)
     */
    @Bean
    @Order(1)
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        http
                .securityMatcher("/api/**")
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .csrf(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/auth/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .requestMatchers("/api/qc/process/**").hasRole("ADMIN")
                        .requestMatchers("/api/analytics/**").hasRole("ADMIN")
                        .requestMatchers("/api/reviewer/**").hasAnyRole("ADMIN", "REVIEWER")
                        .requestMatchers("/api/qc/**").hasAnyRole("ADMIN", "REVIEWER")
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)) // Allow session-based auth as
                                                                                   // fallback
                .authenticationProvider(authenticationProvider())
                .addFilterBefore(jwtAuthFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    /**
     * Security filter chain for web pages - session-based form login
     */
    @Bean
    @Order(2)
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http) throws Exception {
        http
                .securityMatcher("/**")
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                // CSRF disabled: SameSite=Strict cookies + CORS origin allowlist provide equivalent protection
                .csrf(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/css/**", "/js/**", "/images/**", "/webjars/**").permitAll()
                        .requestMatchers("/actuator/health").permitAll()
                        // SECURITY: /files/** — authenticated + ownership enforced in FileController
                        .requestMatchers("/files/**").authenticated()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .requestMatchers("/reviewer/**").hasAnyRole("ADMIN", "REVIEWER")
                        .anyRequest().authenticated())
                .headers(headers -> headers
                        .frameOptions(frameOptions -> frameOptions.sameOrigin())
                        // SECURITY: X-Content-Type-Options prevents MIME sniffing
                        .contentTypeOptions(contentType -> {})
                        // SECURITY: enable HSTS in production behind HTTPS
                        .httpStrictTransportSecurity(hsts -> hsts.disable()))
                .sessionManagement(session -> session
                        // SECURITY: session fixation protection
                        .sessionFixation().migrateSession()
                        .maximumSessions(5)                    // max 5 concurrent sessions per user
                        .maxSessionsPreventsLogin(false))
                .formLogin(form -> form
                        .loginPage("/login")
                        .loginProcessingUrl("/login")
                        .successHandler(authenticationSuccessHandler())
                        .failureUrl("/login?error=true")
                        .permitAll())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutSuccessHandler(logoutSuccessHandler())
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .deleteCookies("JSESSIONID")
                        .permitAll())
                .authenticationProvider(authenticationProvider());

        return http.build();
    }

    /**
     * Custom success handler that logs login and redirects based on user role
     */
    @Bean
    AuthenticationSuccessHandler authenticationSuccessHandler() {
        return (request, response, authentication) -> {
            // Log the login event
            try {
                UserPrincipal userPrincipal = (UserPrincipal) authentication.getPrincipal();
                User user = userPrincipal.getUser();
                String ipAddress = getClientIP(request);
                String userAgent = request.getHeader("User-Agent");

                auditLogService.log(user, "LOGIN", null, null,
                        "Successful login", ipAddress, userAgent);
            } catch (Exception e) {
                // Don't fail login if audit log fails
                e.printStackTrace();
            }

            // Redirect based on role
            var authorities = authentication.getAuthorities();
            String redirectUrl = "/dashboard";

            for (var authority : authorities) {
                String role = authority.getAuthority();
                if (role.equals("ROLE_ADMIN")) {
                    redirectUrl = "/admin/dashboard";
                    break;
                } else if (role.equals("ROLE_REVIEWER")) {
                    redirectUrl = "/reviewer/dashboard";
                    break;
                }
            }

            response.sendRedirect(redirectUrl);
        };
    }

    /**
     * Custom logout handler that logs the logout event
     */
    @Bean
    LogoutSuccessHandler logoutSuccessHandler() {
        return (request, response, authentication) -> {
            // Log the logout event
            try {
                if (authentication != null && authentication.getPrincipal() instanceof UserPrincipal) {
                    UserPrincipal userPrincipal = (UserPrincipal) authentication.getPrincipal();
                    User user = userPrincipal.getUser();
                    String ipAddress = getClientIP(request);
                    String userAgent = request.getHeader("User-Agent");

                    auditLogService.log(user, "LOGOUT", null, null,
                            "User logged out", ipAddress, userAgent);
                }
            } catch (Exception e) {
                // Don't fail logout if audit log fails
                e.printStackTrace();
            }

            response.sendRedirect("/login?logout=true");
        };
    }

    /**
     * Get client IP address handling proxies
     */
    private String getClientIP(jakarta.servlet.http.HttpServletRequest request) {
        String xfHeader = request.getHeader("X-Forwarded-For");
        if (xfHeader == null || xfHeader.isEmpty()) {
            return request.getRemoteAddr();
        }
        return xfHeader.split(",")[0].trim();
    }

    @Bean
    DaoAuthenticationProvider authenticationProvider() {
        DaoAuthenticationProvider authProvider = new DaoAuthenticationProvider(userDetailsService);
        authProvider.setPasswordEncoder(passwordEncoder());
        return authProvider;
    }

    @Bean
    AuthenticationManager authenticationManager() {
        return new ProviderManager(authenticationProvider());
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
