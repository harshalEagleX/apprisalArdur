package com.shal.user.service;

import com.shal.common.entity.Client;
import com.shal.common.entity.Role;
import com.shal.common.entity.User;
import com.shal.common.exception.ResourceNotFoundException;
import com.shal.common.exception.ValidationException;
import com.shal.common.repository.UserRepository;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

/**
 * User accounts.
 *
 * The security-relevant behaviour: a password is NEVER stored as given — it is
 * always run through the encoder — and the minimum length is enforced on both
 * create and reset. A regression in either is a credential-handling bug, not a
 * validation nicety.
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class UserServiceTest {

    @Mock UserRepository userRepository;
    @Mock PasswordEncoder passwordEncoder;

    private UserService svc;

    private UserService service() {
        if (svc == null) svc = new UserService(userRepository, passwordEncoder);
        return svc;
    }

    private static User user(long id, String username) {
        User u = User.builder().username(username).password("hashed").role(Role.REVIEWER).build();
        u.setId(id);
        return u;
    }

    // ── reads ───────────────────────────────────────────────────────────────

    @Test
    @DisplayName("reads delegate to the repository")
    void readsDelegate() {
        when(userRepository.findById(1L)).thenReturn(Optional.of(user(1L, "alice")));
        when(userRepository.findByUsername("alice")).thenReturn(Optional.of(user(1L, "alice")));
        when(userRepository.findAll()).thenReturn(List.of(user(1L, "alice")));
        when(userRepository.findByRole(Role.REVIEWER)).thenReturn(List.of(user(1L, "alice")));
        when(userRepository.findByClientId(5L)).thenReturn(List.of(user(1L, "alice")));
        when(userRepository.count()).thenReturn(2L);
        when(userRepository.countByRole(Role.ADMIN)).thenReturn(1L);

        assertThat(service().findById(1L)).isPresent();
        assertThat(service().findByUsername("alice")).isPresent();
        assertThat(service().findAll()).hasSize(1);
        assertThat(service().findByRole(Role.REVIEWER)).hasSize(1);
        assertThat(service().findByClientId(5L)).hasSize(1);
        assertThat(service().count()).isEqualTo(2L);
        assertThat(service().countByRole(Role.ADMIN)).isEqualTo(1L);
    }

    @Test
    @DisplayName("paged read passes the pageable through")
    void pagedRead() {
        Page<User> page = new PageImpl<>(List.of(user(1L, "alice")));
        when(userRepository.findAll(any(PageRequest.class))).thenReturn(page);
        assertThat(service().findAll(PageRequest.of(0, 20)).getContent()).hasSize(1);
    }

    @Test
    @DisplayName("existsByUsername reflects repository presence")
    void existsByUsername() {
        when(userRepository.findByUsername("taken")).thenReturn(Optional.of(user(1L, "taken")));
        when(userRepository.findByUsername("free")).thenReturn(Optional.empty());
        assertThat(service().existsByUsername("taken")).isTrue();
        assertThat(service().existsByUsername("free")).isFalse();
    }

    // ── create ──────────────────────────────────────────────────────────────

    @Test
    @DisplayName("a new user's password is ENCODED, never stored as given")
    void passwordIsEncodedOnCreate() {
        when(userRepository.findByUsername(anyString())).thenReturn(Optional.empty());
        when(passwordEncoder.encode("plaintext-pw")).thenReturn("ENCODED");
        when(userRepository.save(any())).thenAnswer(i -> i.getArgument(0));

        service().create("  alice  ", "plaintext-pw", Role.REVIEWER, "  a@b.com  ",
                "  Alice A  ", new Client());

        ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);
        verify(userRepository).save(captor.capture());
        User saved = captor.getValue();
        assertThat(saved.getPassword()).isEqualTo("ENCODED");
        assertThat(saved.getPassword()).isNotEqualTo("plaintext-pw");
        // fields are trimmed
        assertThat(saved.getUsername()).isEqualTo("alice");
        assertThat(saved.getEmail()).isEqualTo("a@b.com");
        assertThat(saved.getFullName()).isEqualTo("Alice A");
    }

    @Test
    @DisplayName("null email/full name stay null rather than becoming \"null\"")
    void nullOptionalFieldsStayNull() {
        when(userRepository.findByUsername(anyString())).thenReturn(Optional.empty());
        when(passwordEncoder.encode(anyString())).thenReturn("ENCODED");
        when(userRepository.save(any())).thenAnswer(i -> i.getArgument(0));

        User u = service().create("bob", "password123", Role.ADMIN, null, null, null);
        assertThat(u.getEmail()).isNull();
        assertThat(u.getFullName()).isNull();
    }

    @ParameterizedTest
    @NullSource
    @ValueSource(strings = {"", "   "})
    @DisplayName("a blank username is rejected")
    void blankUsernameRejected(String username) {
        assertThatThrownBy(() -> service().create(username, "password123", Role.ADMIN, null, null, null))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("Username is required");
    }

    @ParameterizedTest
    @NullSource
    @ValueSource(strings = {"", "short", "1234567"})   // 7 chars is one below the floor
    @DisplayName("a password shorter than the minimum is rejected on create")
    void shortPasswordRejectedOnCreate(String pw) {
        assertThatThrownBy(() -> service().create("alice", pw, Role.ADMIN, null, null, null))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("at least " + UserService.PASSWORD_MIN_LENGTH);
    }

    @Test
    @DisplayName("exactly the minimum length is accepted — the boundary is inclusive")
    void minimumLengthPasswordAccepted() {
        when(userRepository.findByUsername(anyString())).thenReturn(Optional.empty());
        when(passwordEncoder.encode(anyString())).thenReturn("ENCODED");
        when(userRepository.save(any())).thenAnswer(i -> i.getArgument(0));
        String exactly = "x".repeat(UserService.PASSWORD_MIN_LENGTH);
        assertThat(service().create("alice", exactly, Role.ADMIN, null, null, null)).isNotNull();
    }

    @Test
    @DisplayName("a null role is rejected — an account must not exist without one")
    void nullRoleRejected() {
        assertThatThrownBy(() -> service().create("alice", "password123", null, null, null, null))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("Role is required");
    }

    @Test
    @DisplayName("a duplicate username is rejected before any save")
    void duplicateUsernameRejected() {
        when(userRepository.findByUsername("alice")).thenReturn(Optional.of(user(1L, "alice")));
        assertThatThrownBy(() -> service().create("alice", "password123", Role.ADMIN, null, null, null))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("already exists");
        verify(userRepository, never()).save(any());
    }

    // ── password reset ──────────────────────────────────────────────────────

    @Test
    @DisplayName("a password reset also encodes, and never writes the raw value")
    void passwordResetEncodes() {
        User existing = user(1L, "alice");
        when(userRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(passwordEncoder.encode("new-password")).thenReturn("NEW-ENCODED");

        service().updatePassword(1L, "new-password");
        assertThat(existing.getPassword()).isEqualTo("NEW-ENCODED");
        verify(userRepository).save(existing);
    }

    @Test
    @DisplayName("the length floor is enforced on reset too, not just on create")
    void resetEnforcesLength() {
        assertThatThrownBy(() -> service().updatePassword(1L, "short"))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("at least " + UserService.PASSWORD_MIN_LENGTH);
        verify(userRepository, never()).save(any());
    }

    @Test
    @DisplayName("a reset needs an id")
    void resetRequiresId() {
        assertThatThrownBy(() -> service().updatePassword(null, "password123"))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("ID is required");
    }

    @Test
    @DisplayName("resetting an unknown user is a not-found")
    void resetUnknownUserThrows() {
        when(userRepository.findById(9L)).thenReturn(Optional.empty());
        assertThatThrownBy(() -> service().updatePassword(9L, "password123"))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    // ── update / activate / delete ──────────────────────────────────────────

    @Test
    @DisplayName("update applies only the fields supplied")
    void updateAppliesSuppliedFields() {
        User existing = user(1L, "alice");
        existing.setEmail("old@b.com");
        when(userRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(userRepository.save(any())).thenAnswer(i -> i.getArgument(0));

        User updated = service().update(1L, "new@b.com", "New Name", Role.ADMIN, null);
        assertThat(updated.getEmail()).isEqualTo("new@b.com");
        assertThat(updated.getFullName()).isEqualTo("New Name");
        assertThat(updated.getRole()).isEqualTo(Role.ADMIN);
    }

    @Test
    @DisplayName("setActive toggles the flag in both directions")
    void setActiveToggles() {
        User existing = user(1L, "alice");
        when(userRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(userRepository.save(any())).thenAnswer(i -> i.getArgument(0));

        assertThat(service().setActive(1L, false).getActive()).isFalse();
        assertThat(service().setActive(1L, true).getActive()).isTrue();
    }

    @Test
    @DisplayName("delete removes an existing user; a missing one is a not-found")
    void deleteBehaviour() {
        when(userRepository.findById(1L)).thenReturn(Optional.of(user(1L, "alice")));
        service().delete(1L);
        verify(userRepository).deleteById(1L);

        when(userRepository.findById(9L)).thenReturn(Optional.empty());
        assertThatThrownBy(() -> service().delete(9L)).isInstanceOf(ResourceNotFoundException.class);

        assertThatThrownBy(() -> service().delete(null))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("ID is required");
    }
}
