package com.apprisal.common.entity;

/**
 * Final decision enum for reviewer verification outcome.
 * 
 * PASS: Reviewer cleared all VERIFY items or no review was required
 * FAIL: Reviewer rejected one or more items
 */
public enum FinalDecision {
    PASS, // Verified and approved
    FAIL // Rejected
}
