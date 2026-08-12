package com.shal.controller.api;

import com.shal.qc.service.PythonClientService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.HttpStatusCodeException;

/**
 * AMC checklists, editable from the admin UI.
 *
 * <p>The checklist lives in SHALqc because SHALqc is what evaluates it. The
 * browser cannot reach SHALqc directly — it only ever talks to this service,
 * and the shared API key must never reach a browser — so this controller is the
 * bridge that makes a previously static YAML editable by a person.
 *
 * <p>Keyed by (client, form version) because 2.6 and 3.6 are different
 * documents, not revisions of one: different wording, different numbering, and
 * different item fields. Bodies are relayed as opaque JSON rather than mapped to
 * a DTO so that a version — or the UI — can carry a field this service has never
 * been taught about. Mapping here would silently drop unknown keys, which on a
 * config screen means the user saves, sees success, and loses their change.
 *
 * <p>All endpoints require ROLE_ADMIN (enforced in SecurityConfig alongside the
 * rest of /api/admin).
 */
@RestController
@RequestMapping("/api/admin/checklists")
public class ChecklistApiController {

    private static final Logger log = LoggerFactory.getLogger(ChecklistApiController.class);

    private final PythonClientService python;

    public ChecklistApiController(PythonClientService python) {
        this.python = python;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> list() {
        String body = python.listChecklists();
        return body == null ? unavailable() : ResponseEntity.ok(body);
    }

    @GetMapping(value = "/{amcCode}/{uadVersion}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> get(@PathVariable String amcCode,
                                      @PathVariable String uadVersion) {
        String body = python.getChecklist(amcCode, uadVersion);
        return body == null ? unavailable() : ResponseEntity.ok(body);
    }

    /**
     * Replace one client's checklist for one form version.
     *
     * <p>SHALqc validates and answers 400 with a message written for the
     * operator ("duplicate rule_id 'X-1' — verdicts are keyed by it…"). That
     * message is passed straight through: a config screen reporting a generic
     * failure leaves the user with nothing to act on.
     */
    @PutMapping(value = "/{amcCode}/{uadVersion}",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> save(@PathVariable String amcCode,
                                       @PathVariable String uadVersion,
                                       @RequestBody String body) {
        try {
            return ResponseEntity.ok(python.saveChecklist(amcCode, uadVersion, body));
        } catch (HttpStatusCodeException e) {
            log.warn("checklist save rejected for {}/{}: {}", amcCode, uadVersion,
                     e.getStatusCode());
            return ResponseEntity.status(e.getStatusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(e.getResponseBodyAsString());
        } catch (Exception e) {
            log.error("checklist save failed for {}/{}: {}", amcCode, uadVersion,
                      e.getMessage());
            return unavailable();
        }
    }

    /** Fork the built-in catalogue into this client's own editable copy. */
    @PostMapping(value = "/{amcCode}/{uadVersion}/seed",
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> seed(@PathVariable String amcCode,
                                       @PathVariable String uadVersion) {
        try {
            return ResponseEntity.ok(python.seedChecklist(amcCode, uadVersion));
        } catch (HttpStatusCodeException e) {
            return ResponseEntity.status(e.getStatusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(e.getResponseBodyAsString());
        } catch (Exception e) {
            log.error("checklist seed failed for {}/{}: {}", amcCode, uadVersion,
                      e.getMessage());
            return unavailable();
        }
    }

    /**
     * SHALqc is down. Said explicitly rather than as an empty list, because an
     * empty checklist screen reads as "this client has no checks configured" —
     * and someone would reasonably start typing them in again.
     */
    private ResponseEntity<String> unavailable() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"detail\":\"The QC service is not reachable, so checklists "
                      + "cannot be loaded or saved right now. Nothing has been changed.\"}");
    }
}
