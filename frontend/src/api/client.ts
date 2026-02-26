/**
 * Axios HTTP client and typed API methods for the VeriDoc backend.
 *
 * Requirements: 8.1, 8.2
 */

import axios from "axios";
import type { Analysis, Claim, ViolationReport } from "@/types";

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
};

export default api;
