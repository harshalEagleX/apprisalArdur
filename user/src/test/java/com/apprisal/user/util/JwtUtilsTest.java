package com.apprisal.user.util;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.security.SignatureException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Date;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * Pure unit coverage for the JWT issue/verify path (user module, no Spring context).
 *
 * Security-critical: a token signed by a different key, or a tampered token, must be
 * rejected; a valid token must round-trip its subject. Also pins the real token TTL
 * (24h) so the value is reviewed deliberately if it ever changes — a too-long TTL is
 * a security risk, a too-short one breaks long-running flows.
 */
class JwtUtilsTest {

    // Same shape as the application.yml default; treated as BASE64, decodes to >32 bytes (HS256 needs >=256 bit).
    private static final String SECRET =
            "404E635266556A586E3272357538782F413F4428472B4B6250645367566B5970";
    private static final String OTHER_SECRET =
            "5A7234753778214125442A472D4B6150645367566B59703373367639792F4233";

    private JwtUtils jwtUtils;
    private final UserDetails alice = User.withUsername("alice@example.com").password("x").authorities("ADMIN").build();
    private final UserDetails bob   = User.withUsername("bob@example.com").password("x").authorities("REVIEWER").build();

    @BeforeEach
    void setUp() {
        jwtUtils = new JwtUtils();
        ReflectionTestUtils.setField(jwtUtils, "secretKey", SECRET);
    }

    @Test
    void roundTripsSubject() {
        String token = jwtUtils.generateToken(alice);
        assertThat(jwtUtils.extractUsername(token)).isEqualTo("alice@example.com");
    }

    @Test
    void validForIssuingUser_invalidForAnother() {
        String token = jwtUtils.generateToken(alice);
        assertThat(jwtUtils.isTokenValid(token, alice)).isTrue();
        assertThat(jwtUtils.isTokenValid(token, bob)).isFalse();
    }

    @Test
    void ttlIsTwentyFourHours() {
        Date issued = new Date();
        String token = jwtUtils.generateToken(alice);
        Date exp = jwtUtils.extractClaim(token, Claims::getExpiration);
        long hours = (exp.getTime() - issued.getTime()) / (1000 * 60 * 60);
        // 24h, not ~1 minute. (Corrects an earlier mis-measurement from load testing.)
        assertThat(hours).isBetween(23L, 24L);
    }

    @Test
    void tokenSignedWithDifferentKeyIsRejected() {
        JwtUtils other = new JwtUtils();
        ReflectionTestUtils.setField(other, "secretKey", OTHER_SECRET);
        String foreignToken = other.generateToken(alice);
        assertThatThrownBy(() -> jwtUtils.extractUsername(foreignToken))
                .isInstanceOf(SignatureException.class);
    }

    @Test
    void tamperedTokenIsRejected() {
        String token = jwtUtils.generateToken(alice);
        // Flip the last character of the payload/signature region.
        String tampered = token.substring(0, token.length() - 2)
                + (token.charAt(token.length() - 1) == 'A' ? "B" : "A");
        assertThatThrownBy(() -> jwtUtils.extractUsername(tampered))
                .isInstanceOf(Exception.class);
    }
}
