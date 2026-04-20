package com.apprisal.dto;

import com.apprisal.entity.Role;

public class RegisterRequest {
    private String username;
    private String password;
    private Role role;

    public RegisterRequest() {
    }

    public RegisterRequest(String username, String password, Role role) {
        this.username = username;
        this.password = password;
        this.role = role;
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public Role getRole() {
        return role;
    }

    public void setRole(Role role) {
        this.role = role;
    }

    public static RegisterRequestBuilder builder() {
        return new RegisterRequestBuilder();
    }

    public static class RegisterRequestBuilder {
        private String username;
        private String password;
        private Role role;

        public RegisterRequestBuilder username(String username) {
            this.username = username;
            return this;
        }

        public RegisterRequestBuilder password(String password) {
            this.password = password;
            return this;
        }

        public RegisterRequestBuilder role(Role role) {
            this.role = role;
            return this;
        }

        public RegisterRequest build() {
            return new RegisterRequest(username, password, role);
        }
    }
}
