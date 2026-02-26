/**
 * TanStack Query hooks for the VeriDoc analysis API.
 *
 * Requirements: 8.1, 8.4
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { analysisApi } from "@/api/client";
import type { Analysis, Claim, ViolationReport } from "@/types";

// ---------------------------------------------------------------------------
// Query key factory — keeps cache keys consistent across hooks.
// ---------------------------------------------------------------------------

export const analysisKeys = {
  all: ["analyses"] as const,
  lists: () => [...analysisKeys.all, "list"] as const,
  detail: (id: string) => [...analysisKeys.all, "detail", id] as const,
  violations: (id: string) => [...analysisKeys.all, "violations", id] as const,
  claims: (id: string) => [...analysisKeys.all, "claims", id] as const,
};

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

/** Fetch the full list of analyses with background refetch. */
export function useAnalysisList() {
  return useQuery<Analysis[]>({
    queryKey: analysisKeys.lists(),
    queryFn: async () => {
      const { data } = await analysisApi.list();
      return data;
    },
    refetchOnWindowFocus: true,
  });
}

/**
 * Fetch a single analysis by ID.
 *
 * Polls every 2 seconds while the analysis is still running.
 * Polling stops once the status reaches "complete" or "failed".
 *
 * Requirement 8.4 — Property 22: Dashboard polling termination.
 */
export function useAnalysis(id: string) {
  return useQuery<Analysis>({
    queryKey: analysisKeys.detail(id),
    queryFn: async () => {
      const { data } = await analysisApi.get(id);
      return data;
    },
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "complete" || status === "failed") {
        return false;
      }
      return 2000;
    },
  });
}

/** Fetch the violation report for a completed analysis. */
export function useViolationReport(id: string) {
  return useQuery<ViolationReport>({
    queryKey: analysisKeys.violations(id),
    queryFn: async () => {
      const { data } = await analysisApi.getViolations(id);
      return data;
    },
    enabled: !!id,
  });
}

/** Fetch extracted claims for an analysis. */
export function useClaims(id: string) {
  return useQuery<Claim[]>({
    queryKey: analysisKeys.claims(id),
    queryFn: async () => {
      const { data } = await analysisApi.getClaims(id);
      return data;
    },
    enabled: !!id,
  });
}

/**
 * Mutation to create a new analysis.
 *
 * Invalidates the analysis list cache on success so the dashboard
 * picks up the new entry immediately.
 */
export function useCreateAnalysis() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (formData: FormData) => {
      const { data } = await analysisApi.create(formData);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: analysisKeys.lists() });
    },
  });
}
