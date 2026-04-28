package com.apprisal.common.dto;

import com.apprisal.common.entity.Role;

public record RegisterRequest(String username, String password, Role role) {}
