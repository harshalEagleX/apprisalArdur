package com.apprisal.entity;

/**
 * Final decision enum for reviewer verification outcome.
 * 
 * PASS: Reviewer verified all warnings as acceptable
 * FAIL: Reviewer rejected one or more items
 */
public enum FinalDecision {
    PASS, // Verified and approved
    FAIL // Rejected
}
