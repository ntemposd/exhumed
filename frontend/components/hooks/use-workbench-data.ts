// Data hooks keep persistence, caching, and backend IO separate from the
// presentational workbench surfaces.
import { useEffect, useState } from "react";

import { backendUrl } from "@/lib/config";
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

export function useAgentsCatalog({ councilStorageKey, cacheKey, cacheTtlMs }: UseAgentsCatalogOptions) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [agentsError, setAgentsError] = useState("");
  const [isLoadingAgents, setIsLoadingAgents] = useState(true);
  const [isRefreshingAgents, setIsRefreshingAgents] = useState(false);
  const [hasHydratedCouncil, setHasHydratedCouncil] = useState(false);

  useEffect(() => {
    // Do not persist selection until the initial hydration has resolved,
    // otherwise a first-render empty array can wipe the saved council.
    if (!hasHydratedCouncil) {
      return;
    }

    window.localStorage.setItem(councilStorageKey, JSON.stringify(selectedAgents));
  }, [councilStorageKey, hasHydratedCouncil, selectedAgents]);

  useEffect(() => {
    let cancelled = false;

    function getHydratedCouncilIds(nextAgents: Agent[]) {
      // Council hydration is filtered against the currently available agent ids
      // so stale local selections cannot reference missing backend records.
      const storedCouncilIds = window.localStorage.getItem(councilStorageKey);
      const parsedCouncilIds = storedCouncilIds ? (JSON.parse(storedCouncilIds) as string[]) : [];
      const availableIds = new Set(nextAgents.map((agent) => agent.agent_id));
      const hydratedCouncilIds = parsedCouncilIds.filter((agentId) => availableIds.has(agentId));

      return hydratedCouncilIds.length > 0 ? hydratedCouncilIds : getDefaultCouncilAgentIds(nextAgents);
    }

    async function loadAgents() {
      setAgentsError("");
      const cachedValue = window.localStorage.getItem(cacheKey);
      let hasCachedAgents = false;

      if (cachedValue) {
        try {
          const parsedCache = JSON.parse(cachedValue) as {
            cachedAt?: number;
            data?: AgentsResponse;
          };

          if (Array.isArray(parsedCache.data?.agents)) {
            const cachedAgents = parsedCache.data.agents;
            setAgents(cachedAgents);
            setSelectedAgents(getHydratedCouncilIds(cachedAgents));
            setHasHydratedCouncil(true);
            hasCachedAgents = true;
          }

          if (
            typeof parsedCache.cachedAt === "number" &&
            Array.isArray(parsedCache.data?.agents) &&
            Date.now() - parsedCache.cachedAt < cacheTtlMs
          ) {
            setIsLoadingAgents(false);
            setIsRefreshingAgents(false);
            return;
          }
        } catch {
          window.localStorage.removeItem(cacheKey);
        }
      }

      setIsLoadingAgents(!hasCachedAgents);
      setIsRefreshingAgents(hasCachedAgents);

      try {
        const response = await fetch(`${backendUrl}/agents`, {
          headers: { Accept: "application/json" },
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`);
        }

        const data = (await response.json()) as AgentsResponse;
        if (cancelled) {
          return;
        }

        const nextAgents = Array.isArray(data.agents) ? data.agents : [];
        setAgents(nextAgents);
        setSelectedAgents(getHydratedCouncilIds(nextAgents));
        setHasHydratedCouncil(true);
        window.localStorage.setItem(
          cacheKey,
          JSON.stringify({
            cachedAt: Date.now(),
            data,
          }),
        );
      } catch (loadError) {
        if (cancelled) {
          return;
        }

        const message = loadError instanceof Error ? loadError.message : "Unknown backend error";
        setAgentsError(message);
      } finally {
        if (!cancelled) {
          setIsLoadingAgents(false);
          setIsRefreshingAgents(false);
          setHasHydratedCouncil(true);
        }
      }
    }

    void loadAgents();

    return () => {
      cancelled = true;
    };
  }, [cacheKey, cacheTtlMs, councilStorageKey]);

  return {
    agents,
    selectedAgents,
    setSelectedAgents,
    agentsError,
    isLoadingAgents,
    isRefreshingAgents,
  };
}

export function useServicesStatus({ cacheKey, cacheTtlMs }: UseServicesStatusOptions) {
  const [services, setServices] = useState<ServicesStatusResponse | null>(null);
  const [servicesError, setServicesError] = useState("");
  const [isLoadingServices, setIsLoadingServices] = useState(true);
  const [isRefreshingServices, setIsRefreshingServices] = useState(false);

  useEffect(() => {
    // Services use stale-while-revalidate semantics: cached data renders first,
    // then an asynchronous refresh updates the panel in the background.
    let cancelled = false;

    async function loadServices() {
      const cachedValue = window.localStorage.getItem(cacheKey);
      let hasCachedServices = false;

      if (cachedValue) {
        try {
          const parsedCache = JSON.parse(cachedValue) as {
            cachedAt?: number;
            data?: ServicesStatusResponse;
          };

          if (parsedCache.data) {
            setServices(parsedCache.data);
            setServicesError("");
            hasCachedServices = true;
          }

          if (
            typeof parsedCache.cachedAt === "number" &&
            parsedCache.data &&
            Date.now() - parsedCache.cachedAt < cacheTtlMs
          ) {
            setIsLoadingServices(false);
            setIsRefreshingServices(false);
            return;
          }
        } catch {
          window.localStorage.removeItem(cacheKey);
        }
      }

      setIsLoadingServices(!hasCachedServices);
      setIsRefreshingServices(hasCachedServices);

      try {
        const response = await fetch(`${backendUrl}/services-status`, {
          headers: { Accept: "application/json" },
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error(`Status probe failed with ${response.status}`);
        }

        const data = (await response.json()) as ServicesStatusResponse;
        if (cancelled) {
          return;
        }

        setServices(data);
        setServicesError("");
        window.localStorage.setItem(
          cacheKey,
          JSON.stringify({
            cachedAt: Date.now(),
            data,
          }),
        );
      } catch (loadError) {
        if (cancelled) {
          return;
        }

        const message = loadError instanceof Error ? loadError.message : "Could not load service status";
        setServicesError(message);
      } finally {
        if (!cancelled) {
          setIsLoadingServices(false);
          setIsRefreshingServices(false);
        }
      }
    }

    void loadServices();

    return () => {
      cancelled = true;
    };
  }, [cacheKey, cacheTtlMs]);

  return {
    services,
    servicesError,
    isLoadingServices,
    isRefreshingServices,
  };
}