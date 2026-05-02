package com.apprisal.common.dto;

public record DecisionSaveRequest(
        Long ruleResultId,
        String decision,
        String comment,
        String sessionToken,
        Long decisionLatencyMs,
        Boolean acknowledged
) {}
