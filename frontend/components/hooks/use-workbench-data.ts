// Data hooks keep persistence, caching, and backend IO separate from the
// presentational workbench surfaces.
import { useEffect, useRef, useState } from "react";

import { backendUrl } from "@/lib/config";
import { apiFetch, getRequestFailureMessage, getResponseErrorMessage } from "@/lib/http";
import type { Agent, AgentsResponse, ServicesStatusResponse } from "@/lib/types";

import { getDefaultCouncilAgentIds } from "../utils";

type UseAgentsCatalogOptions = {
  councilStorageKey: string;
  cacheKey: string;
  cacheTtlMs: number;
};

type UseServicesStatusOptions = {
  cacheKey: string;
  cacheTtlMs: number;
};

// ─── Generic stale-while-revalidate cache hook ────────────────────────────

type CachedFetchOptions<T> = {
  cacheKey: string;
  cacheTtlMs: number;
  url: string;
  errorMessage: string;
  /** Validate and transform raw JSON. Return null to treat the payload as invalid. */
  transform: (raw: unknown) => T | null;
  /** Called with validated data on both cache hits and successful network fetches. */
  onResult: (data: T) => void;
};

function useCachedFetch<T>({
  cacheKey,
  cacheTtlMs,
  url,
  errorMessage,
  transform,
  onResult,
}: CachedFetchOptions<T>) {
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Refs keep callbacks always current without adding them to the effect deps,
  // which would otherwise cause infinite re-fetch loops for inline-defined functions.
  const transformRef = useRef(transform);
  const onResultRef = useRef(onResult);
  transformRef.current = transform;
  onResultRef.current = onResult;

  useEffect(() => {
    let cancelled = false;
    const abortController = new AbortController();

    async function load() {
      const cachedValue = window.localStorage.getItem(cacheKey);
      let hasCachedData = false;

      if (cachedValue) {
        try {
          const parsed = JSON.parse(cachedValue) as { cachedAt?: number; data?: unknown };
          const result = parsed.data != null ? transformRef.current(parsed.data) : null;

          if (result !== null) {
            setError("");
            onResultRef.current(result);
            hasCachedData = true;

            if (typeof parsed.cachedAt === "number" && Date.now() - parsed.cachedAt < cacheTtlMs) {
              setIsLoading(false);
              setIsRefreshing(false);
              return;
            }
          }
        } catch {
          window.localStorage.removeItem(cacheKey);
        }
      }

      setIsLoading(!hasCachedData);
      setIsRefreshing(hasCachedData);

      try {
        const response = await apiFetch(url, {
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal: abortController.signal,
        });

        if (!response.ok) {
          throw new Error(await getResponseErrorMessage(response, errorMessage));
        }

        const data = (await response.json()) as unknown;
        if (cancelled) return;

        const result = transformRef.current(data);
        if (result !== null) {
          setError("");
          onResultRef.current(result);
          window.localStorage.setItem(cacheKey, JSON.stringify({ cachedAt: Date.now(), data }));
        }
      } catch (loadError) {
        if (cancelled) return;
        setError(getRequestFailureMessage(loadError, errorMessage));
      } finally {
        if (!cancelled) {
          setIsLoading(false);
          setIsRefreshing(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
      abortController.abort();
    };
  }, [cacheKey, cacheTtlMs, url, errorMessage]);

  return { error, isLoading, isRefreshing };
}

// ─── useAgentsCatalog ─────────────────────────────────────────────────────

export function useAgentsCatalog({ councilStorageKey, cacheKey, cacheTtlMs }: UseAgentsCatalogOptions) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [hasHydratedCouncil, setHasHydratedCouncil] = useState(false);

  useEffect(() => {
    // Do not persist selection until the initial hydration has resolved,
    // otherwise a first-render empty array can wipe the saved council.
    if (!hasHydratedCouncil) return;
    window.localStorage.setItem(councilStorageKey, JSON.stringify(selectedAgents));
  }, [councilStorageKey, hasHydratedCouncil, selectedAgents]);

  function getHydratedCouncilIds(nextAgents: Agent[]) {
    // Council hydration is filtered against currently available agent IDs so
    // stale local selections cannot reference missing backend records.
    const storedCouncilIds = window.localStorage.getItem(councilStorageKey);
    const parsedCouncilIds = storedCouncilIds ? (JSON.parse(storedCouncilIds) as string[]) : [];
    const availableIds = new Set(nextAgents.map((agent) => agent.agent_id));
    const hydratedCouncilIds = parsedCouncilIds.filter((agentId) => availableIds.has(agentId));
    return hydratedCouncilIds.length > 0 ? hydratedCouncilIds : getDefaultCouncilAgentIds(nextAgents);
  }

  const { error: agentsError, isLoading: isLoadingAgents, isRefreshing: isRefreshingAgents } =
    useCachedFetch<AgentsResponse>({
      cacheKey,
      cacheTtlMs,
      url: `${backendUrl}/agents`,
      errorMessage: "Could not load the agent catalog",
      transform: (raw) => {
        const data = raw as AgentsResponse;
        return Array.isArray(data?.agents) ? data : null;
      },
      onResult: (data) => {
        const nextAgents = Array.isArray(data.agents) ? data.agents : [];
        setAgents(nextAgents);
        setSelectedAgents(getHydratedCouncilIds(nextAgents));
        setHasHydratedCouncil(true);
      },
    });

  return {
    agents,
    selectedAgents,
    setSelectedAgents,
    agentsError,
    isLoadingAgents,
    isRefreshingAgents,
  };
}

// ─── useServicesStatus ────────────────────────────────────────────────────

export function useServicesStatus({ cacheKey, cacheTtlMs }: UseServicesStatusOptions) {
  const [services, setServices] = useState<ServicesStatusResponse | null>(null);

  const { error: servicesError, isLoading: isLoadingServices, isRefreshing: isRefreshingServices } =
    useCachedFetch<ServicesStatusResponse>({
      cacheKey,
      cacheTtlMs,
      url: `${backendUrl}/services-status`,
      errorMessage: "Could not load backend service status",
      transform: (raw) => (raw != null ? (raw as ServicesStatusResponse) : null),
      onResult: setServices,
    });

  return { services, servicesError, isLoadingServices, isRefreshingServices };
}
