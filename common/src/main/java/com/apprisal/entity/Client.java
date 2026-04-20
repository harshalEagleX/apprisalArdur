package com.apprisal.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

import org.hibernate.envers.Audited;

/**
 * Client organization entity.
 */
@Entity
@Audited
@Table(name = "client")
public class Client extends BaseEntity {

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String code;

    @Column(nullable = false)
    private String status = "ACTIVE";

    public Client() {
    }

    public Client(Long id, String name, String code, String status) {
        this.setId(id);
        this.name = name;
        this.code = code;
        this.status = status;
    }

    // Getters and Setters
    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    // Builder pattern
    public static ClientBuilder builder() {
        return new ClientBuilder();
    }

    public static class ClientBuilder {
        private Long id;
        private String name;
        private String code;
        private String status = "ACTIVE";

        public ClientBuilder id(Long id) {
            this.id = id;
            return this;
        }

        public ClientBuilder name(String name) {
            this.name = name;
            return this;
        }

        public ClientBuilder code(String code) {
            this.code = code;
            return this;
        }

        public ClientBuilder status(String status) {
            this.status = status;
            return this;
        }

        public Client build() {
            return new Client(id, name, code, status);
        }
    }
}
