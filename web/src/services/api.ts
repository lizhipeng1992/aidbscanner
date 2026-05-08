import axios from "axios";
import type {
  DatabaseListResponse,
  TableListResponse,
  FieldSemanticResponse,
  TableSemanticResponse,
  RelationshipResponse,
  RelationshipVerifyRequest,
  HealthResponse,
  ScanRequest,
  ScanResult,
  ReviewPendingResponse,
  ReviewSubmitRequest,
  ReviewRejectRequest,
  ReviewModifyRequest,
  ReviewResultResponse,
  QueryRequest,
  QueryResponse,
  FieldSemanticCacheResponse,
  UpdateFieldSemanticRequest,
  UpdateTableSemanticRequest,
} from "../types/api";

const api = axios.create({
  baseURL: "/api",
  timeout: 300000,
  headers: { "Content-Type": "application/json" },
});

// Request interceptor
api.interceptors.request.use(
  (config) => {
    console.log("[API] →", config.method?.toUpperCase(), config.url, config.data || config.params);
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail;
    console.error("[API] ← Error", error.response?.status, detail || error.message);
    return Promise.reject(error);
  }
);

// Health
export const getHealth = () => api.get<HealthResponse>("/health");

// Databases
export const getDatabases = () => api.get<DatabaseListResponse>("/databases");

// Tables
export const getTables = (dbName: string) =>
  api.get<TableListResponse>(`/databases/${encodeURIComponent(dbName)}/tables`);

// Field analysis
export const analyzeField = (dbName: string, tableName: string, columnName: string) =>
  api.post<FieldSemanticResponse>("/fields/analyze", {
    db_name: dbName,
    table_name: tableName,
    column_name: columnName,
  });

// Table analysis
export const analyzeTable = (dbName: string, tableName: string, sampleSize = 5) =>
  api.post<TableSemanticResponse>("/tables/analyze", {
    db_name: dbName,
    table_name: tableName,
    sample_size: sampleSize,
  });

// Relationships
export const discoverRelationships = (dbName: string) =>
  api.post<RelationshipResponse[]>(`/discover/relationships`, null, {
    params: { db_name: dbName },
  });

export const verifyRelationship = (data: RelationshipVerifyRequest) =>
  api.post<RelationshipResponse>("/relationships/verify", data);

// Scan
export const fullScan = (request: ScanRequest) =>
  api.post<unknown, { data: ScanResult }>("/scan", request);

// Review
export const getPendingReviews = (dbName?: string) => {
  const params = dbName ? { db_name: dbName } : undefined;
  return api.get<ReviewPendingResponse>("/review/pending", { params });
};

export const submitReview = (request: ReviewSubmitRequest) =>
  api.post<ReviewResultResponse>("/review/submit", request);

export const rejectReview = (request: ReviewRejectRequest) =>
  api.post<ReviewResultResponse>("/review/reject", request);

export const modifyReview = (request: ReviewModifyRequest) =>
  api.post<ReviewResultResponse>("/review/modify", request);

// Query
export const query = (request: QueryRequest) =>
  api.post<QueryResponse>("/query", request);

// Semantic Cache
export const getTableSemanticCache = (dbName: string, tableName: string) =>
  api.get<FieldSemanticCacheResponse>(`/databases/${encodeURIComponent(dbName)}/tables/${encodeURIComponent(tableName)}/semantic`);

export const getFieldSemanticCache = (dbName: string, tableName: string, columnName: string) =>
  api.get<FieldSemanticCacheResponse>(`/databases/${encodeURIComponent(dbName)}/tables/${encodeURIComponent(tableName)}/field/${encodeURIComponent(columnName)}/semantic`);

export const updateFieldSemantic = (request: UpdateFieldSemanticRequest) =>
  api.put<FieldSemanticResponse>("/fields/semantic", request);

export const updateTableSemantic = (request: UpdateTableSemanticRequest) =>
  api.put<TableSemanticResponse>("/tables/semantic", request);

export default api;
