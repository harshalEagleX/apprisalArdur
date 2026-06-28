package com.shal.common.entity;

/**
 * File type enum for batch files.
 */
public enum FileType {
    APPRAISAL,      // Appraisal report PDF
    APPRAISAL_XML,  // MISMO 2.6 GSE appraisal XML (always paired with an APPRAISAL)
    ENGAGEMENT,     // Engagement letter / order form PDF
    CONTRACT        // Purchase contract / purchase agreement PDF
}
