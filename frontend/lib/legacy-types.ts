// Legacy types used by the old UploadScreen / ResultsDashboard / RuleDetailView components
// These components connect to the Python service directly on port 5001

export type RuleResult = {
  rule_id: string;
  rule_name: string;
  status: string;
  message: string;
  action_item?: string;
  appraisal_value?: string;
  engagement_value?: string;
  review_required: boolean;
  severity: string;
  source_page?: number;
  field_confidence?: number;
};

export type QCResults = {
  success: boolean;
  processing_time_ms: number;
  total_pages: number;
  extraction_method: string;
  total_rules: number;
  passed: number;
  failed: number;
  verify: number;
  document_id?: string;
  cache_hit: boolean;
  file_hash: string;
  extracted_fields: Record<string, unknown>;
  field_confidence: Record<string, number>;
  rule_results: RuleResult[];
  action_items: string[];
};
