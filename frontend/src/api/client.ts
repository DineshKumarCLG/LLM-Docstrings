/**
 * Axios HTTP client and typed API methods for the VeriDoc backend.
 *
 * Requirements: 8.1, 8.2
 */

import axios from "axios";
import type { Analysis, Claim, ViolationReport, BatchResult, DocumentationTree, FileWithPath, LLMProvider } from "@/types";

// ---------------------------------------------------------------------------
// Axios instance — all requests go through the /api prefix.
// In development Vite proxies /api to the FastAPI backend.
// ---------------------------------------------------------------------------

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

// ---------------------------------------------------------------------------
// Typed API surface
// ---------------------------------------------------------------------------

export const analysisApi = {
  /** Create a new analysis (file upload or code paste). */
  create: (data: FormData) =>
    api.post<{ analysis_id: string }>("/analyses", data, {
      headers: { "Content-Type": "multipart/form-data" },
    }),

  /** List all analyses. */
  list: () => api.get<Analysis[]>("/analyses"),

  /** Get a single analysis by ID (status + summary). */
  get: (id: string) => api.get<Analysis>(`/analyses/${id}`),

  /** Get extracted claims for an analysis. */
  getClaims: (id: string) => api.get<Claim[]>(`/analyses/${id}/claims`),

  /** Get the full violation report for an analysis. */
  getViolations: (id: string) =>
    api.get<ViolationReport>(`/analyses/${id}/violations`),

  /** Export the violation report in the given format (json | csv | pdf). */
  export: (id: string, format: string) =>
    api.get(`/analyses/${id}/export`, {
      params: { format },
      responseType: "blob",
    }),

  /** Delete an analysis and all associated data. */
  delete: (id: string) => api.delete(`/analyses/${id}`),

  /** Create a batch analysis from a ZIP file. */
  createBatch: (data: FormData) =>
    api.post<{ batch_id: string; analysis_ids: string[]; total: number }>(
      "/analyses/batch",
      data,
      { headers: { "Content-Type": "multipart/form-data" } }
    ),

  /**
   * Create a batch analysis from folder-selected files.
   *
   * Bundles an array of FileWithPath objects into multipart FormData
   * and submits to the batch endpoint.
   *
   * Requirements: 7.8, 8.1
   */
  createBatchFromFolder: (files: FileWithPath[], llmProvider: LLMProvider) => {
    const formData = new FormData();
    formData.append("llm_provider", llmProvider);
    for (const fwp of files) {
      formData.append("files", fwp.file, fwp.relativePath);
    }
    return api.post<{ batch_id: string; analysis_ids: string[]; total: number }>(
      "/analyses/batch",
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
  },

  /** Get batch status — all analyses in a batch. */
  getBatch: (batchId: string) => api.get<BatchResult>(`/batches/${batchId}`),

  /** Get the documentation tree for a completed analysis. */
  getDocumentation: (id: string) =>
    api.get<DocumentationTree>(`/analyses/${id}/documentation`),
};

export default api;
