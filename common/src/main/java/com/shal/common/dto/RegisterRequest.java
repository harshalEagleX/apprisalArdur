package com.shal.common.dto;

import com.shal.common.entity.Role;

public record RegisterRequest(String username, String password, Role role) {}
