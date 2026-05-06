export const fullLifecycleScenario = {
  name: "full-lifecycle",
  goal: "Simulate admin batch processing and reviewer sign-off until the batch reaches COMPLETED.",
  actors: ["ADMIN", "REVIEWER"],
  expectedStates: ["UPLOADED", "QC_PROCESSING", "REVIEW_PENDING", "IN_REVIEW", "COMPLETED"],
  validations: [
    "Admin can access batch workspace.",
    "Reviewer can access assigned queue.",
    "Backend state reaches REVIEW_PENDING before reviewer work starts.",
    "Reviewer saves every required rule decision.",
    "Review submit transitions the batch to COMPLETED."
  ]
} as const;
