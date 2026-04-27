package com.apprisal.dto;

import com.apprisal.entity.Role;

public record RegisterRequest(String username, String password, Role role) {}
