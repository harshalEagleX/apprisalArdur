package com.shal.user.service;

import com.shal.common.entity.Client;
import com.shal.common.exception.ResourceNotFoundException;
import com.shal.common.exception.ValidationException;
import com.shal.common.repository.ClientRepository;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Client CRUD.
 *
 * A client CODE is the key SHALqc resolves an AMC's compiled checklist bundle by,
 * so its normalisation (trim + upper) and uniqueness are not cosmetic: a stray
 * lower-case or padded code silently resolves the wrong bundle, or none.
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class ClientServiceTest {

    @Mock ClientRepository clientRepository;
    @InjectMocks ClientService svc;

    private static Client client(long id, String name) {
        Client c = Client.builder().name(name).code("EQ").status("ACTIVE").build();
        c.setId(id);
        return c;
    }

    // ── reads ───────────────────────────────────────────────────────────────

    @Test
    @DisplayName("reads delegate straight to the repository")
    void readsDelegate() {
        when(clientRepository.findById(1L)).thenReturn(Optional.of(client(1L, "Acme")));
        when(clientRepository.findByCode("EQ")).thenReturn(Optional.of(client(1L, "Acme")));
        when(clientRepository.findAll()).thenReturn(List.of(client(1L, "Acme")));
        when(clientRepository.count()).thenReturn(3L);

        assertThat(svc.findById(1L)).isPresent();
        assertThat(svc.findByCode("EQ")).isPresent();
        assertThat(svc.findAll()).hasSize(1);
        assertThat(svc.count()).isEqualTo(3L);
    }

    @Test
    @DisplayName("a missing client reads as empty, not as an exception")
    void missingReadsEmpty() {
        when(clientRepository.findById(9L)).thenReturn(Optional.empty());
        assertThat(svc.findById(9L)).isEmpty();
    }

    // ── create ──────────────────────────────────────────────────────────────

    @Test
    @DisplayName("a new client's code is trimmed and upper-cased")
    void codeIsNormalised() {
        // SHALqc resolves the compiled bundle by this code — "  eq  " must not
        // become a distinct client from "EQ".
        when(clientRepository.existsByCode("EQ")).thenReturn(false);
        when(clientRepository.save(any())).thenAnswer(i -> i.getArgument(0));

        Client created = svc.create("  Acme Appraisals  ", "  eq  ");

        ArgumentCaptor<Client> captor = ArgumentCaptor.forClass(Client.class);
        verify(clientRepository).save(captor.capture());
        assertThat(captor.getValue().getCode()).isEqualTo("EQ");
        assertThat(captor.getValue().getName()).isEqualTo("Acme Appraisals");
        assertThat(created.getStatus()).isEqualTo("ACTIVE");
    }

    @ParameterizedTest
    @NullSource
    @ValueSource(strings = {"", "   "})
    @DisplayName("a blank name is rejected")
    void blankNameRejected(String name) {
        assertThatThrownBy(() -> svc.create(name, "EQ"))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("name is required");
    }

    @ParameterizedTest
    @NullSource
    @ValueSource(strings = {"", "   "})
    @DisplayName("a blank code is rejected")
    void blankCodeRejected(String code) {
        assertThatThrownBy(() -> svc.create("Acme", code))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("code is required");
    }

    @Test
    @DisplayName("a duplicate code is rejected — checked in NORMALISED form")
    void duplicateCodeRejected() {
        // "  eq  " must collide with an existing "EQ", or two clients end up
        // fighting over the same compiled bundle.
        when(clientRepository.existsByCode("EQ")).thenReturn(true);
        assertThatThrownBy(() -> svc.create("Acme", "  eq  "))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("already exists");
        verify(clientRepository, never()).save(any());
    }

    // ── update ──────────────────────────────────────────────────────────────

    @Test
    @DisplayName("update trims the name and sets the status")
    void updateAppliesChanges() {
        Client existing = client(1L, "Old");
        when(clientRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(clientRepository.save(any())).thenAnswer(i -> i.getArgument(0));

        Client updated = svc.update(1L, "  New Name  ", "INACTIVE");
        assertThat(updated.getName()).isEqualTo("New Name");
        assertThat(updated.getStatus()).isEqualTo("INACTIVE");
    }

    @Test
    @DisplayName("a null or blank name leaves the existing name untouched")
    void updateKeepsNameWhenBlank() {
        Client existing = client(1L, "Original");
        when(clientRepository.findById(1L)).thenReturn(Optional.of(existing));
        when(clientRepository.save(any())).thenAnswer(i -> i.getArgument(0));

        assertThat(svc.update(1L, null, null).getName()).isEqualTo("Original");
        assertThat(svc.update(1L, "   ", null).getName()).isEqualTo("Original");
    }

    @Test
    @DisplayName("updating a client that does not exist is a not-found, not a silent create")
    void updateMissingThrows() {
        when(clientRepository.findById(9L)).thenReturn(Optional.empty());
        assertThatThrownBy(() -> svc.update(9L, "X", "ACTIVE"))
                .isInstanceOf(ResourceNotFoundException.class);
        verify(clientRepository, never()).save(any());
    }

    // ── delete ──────────────────────────────────────────────────────────────

    @Test
    @DisplayName("delete removes an existing client by id")
    void deleteRemoves() {
        when(clientRepository.findById(1L)).thenReturn(Optional.of(client(1L, "Acme")));
        svc.delete(1L);
        verify(clientRepository).deleteById(1L);
    }

    @Test
    @DisplayName("delete requires an id")
    void deleteNullIdRejected() {
        assertThatThrownBy(() -> svc.delete(null))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("ID is required");
        verify(clientRepository, never()).deleteById(any());
    }

    @Test
    @DisplayName("deleting a client that does not exist is a not-found, never a no-op")
    void deleteMissingThrows() {
        when(clientRepository.findById(9L)).thenReturn(Optional.empty());
        assertThatThrownBy(() -> svc.delete(9L))
                .isInstanceOf(ResourceNotFoundException.class);
        verify(clientRepository, never()).deleteById(any());
    }
}
