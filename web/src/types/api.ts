export interface DatabaseListResponse {
  databases: string[];
}

export interface TableMetadataResponse {
  table_name: string;
  table_comment: string | null;
  engine: string;
  columns: ColumnInfo[];
}

export interface ColumnInfo {
  column_name: string;
  table_name: string;
  data_type: string;
  character_maximum_length: number | null;
  is_nullable: boolean;
  column_default: string | null;
  column_comment: string | null;
  is_primary_key: boolean;
  is_auto_increment: boolean;
  ordinal_position: number;
}

export interface TableListResponse {
  database: string;
  tables: TableMetadataResponse[];
}

export interface FieldSemanticResponse {
  id: string;
  db_name: string;
  table_name: string;
  column_name: string;
  data_type: string;
  chinese_name: string | null;
  business_definition: string | null;
  value_rules: string | null;
  related_fields: string[];
  data_category: DataCategory;
  status: FieldStatus;
}

export interface TableSemanticResponse {
  table_name: string;
  db_name: string;
  chinese_name: string | null;
  business_definition: string | null;
  data_category: DataCategory;
  fields: FieldSemanticResponse[];
}

export interface RelationshipResponse {
  source_table: string;
  source_column: string;
  target_table: string;
  target_column: string;
  relationship_type: string;
  match_rate: number;
  verified: boolean;
}

export interface RelationshipVerifyRequest {
  db_name: string;
  source_table: string;
  source_column: string;
  target_table: string;
  target_column: string;
}

export interface HealthResponse {
  status: string;
  database: string;
  llm: string;
  llm_provider: string | null;
  timestamp: string;
}

export interface ScanRequest {
  db_name: string;
  sample_size?: number;
  verify_relationships?: boolean;
}

export interface ScanResult {
  status: string;
  database: string;
  tables: ScanTableResult[];
  relationships: RelationshipResponse[];
}

export interface ScanTableResult {
  table_name: string;
  chinese_name: string | null;
  business_definition: string | null;
  data_category: string;
  fields: ScanFieldResult[];
}

export interface ScanFieldResult {
  column_name: string;
  data_type: string;
  chinese_name: string | null;
  business_definition: string | null;
  data_category: string;
}

export interface ReviewPendingItem {
  id: string;
  db_name: string;
  table_name: string;
  column_name: string;
  data_type: string;
  chinese_name: string | null;
  business_definition: string | null;
  value_rules: string | null;
  related_fields: string[];
  data_category: DataCategory;
  created_at: string;
}

export interface ReviewPendingResponse {
  total: number;
  pending_fields: ReviewPendingItem[];
}

export interface ReviewSubmitRequest {
  field_id: string;
  calibrated_by: string;
  modifications?: Record<string, unknown>;
}

export interface ReviewRejectRequest {
  field_id: string;
  reason?: string;
}

export interface ReviewModifyRequest {
  field_id: string;
  calibrated_by: string;
  modifications: Record<string, unknown>;
}

export interface ReviewResultResponse {
  success: boolean;
  field_id: string;
  status: FieldStatus;
  message: string | null;
}

export interface QueryRequest {
  question: string;
  db_name?: string;
  top_k?: number;
}

export interface QueryFieldResult {
  column_name: string;
  table_name: string;
  db_name: string;
  data_type: string;
  chinese_name: string | null;
  business_definition: string | null;
  value_rules: string | null;
  data_category: DataCategory;
  relevance_score: number;
}

export interface QueryTableResult {
  table_name: string;
  db_name: string;
  chinese_name: string | null;
  business_definition: string | null;
  data_category: DataCategory;
  relevance_score: number;
}

export interface QueryResponse {
  question: string;
  answer: string;
  relevant_fields: QueryFieldResult[];
  relevant_tables: QueryTableResult[];
  has_error: boolean;
  error_message: string | null;
}

export type DataCategory = "dimension" | "metric" | "fact" | "other";
export type FieldStatus = "PENDING" | "CALIBRATED" | "AUTO" | "SKIPPED";

export interface FieldSemanticCacheResponse {
  id: string;
  db_name: string;
  table_name: string;
  column_name: string;
  data_type: string;
  chinese_name: string | null;
  business_definition: string | null;
  value_rules: string | null;
  related_fields: string[];
  data_category: DataCategory;
  status: FieldStatus | null;
  has_semantics: boolean;
  fields?: FieldSemanticCacheResponse[];
}

export interface UpdateTableSemanticRequest {
  db_name: string;
  table_name: string;
  chinese_name?: string | null;
  business_definition?: string | null;
  data_category?: DataCategory;
}

export interface UpdateFieldSemanticRequest {
  field_id: string;
  chinese_name?: string;
  business_definition?: string;
  value_rules?: string;
  data_category?: DataCategory;
}
