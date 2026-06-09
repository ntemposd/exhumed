// This local registry provides presentation metadata for the historical agents
// that the backend exposes. The UI uses it to enrich raw backend records.

// Speakers without ingested corpora stay visible in the catalog but cannot be drafted.
export const UNAVAILABLE_AGENT_IDS = new Set([
  "agt_010", // Jorge Luis Borges — placeholder source file
  "agt_015", // Frida Kahlo — placeholder source file
  "agt_016", // Salvador Dali — placeholder source file
]);

export function isAgentSelectable(agentId: string) {
  return !UNAVAILABLE_AGENT_IDS.has(agentId);
}

const legendCatalog = [
  { agent_id: "agt_001", display_name: "Socrates", archetype: "The Questioner" },
  { agent_id: "agt_002", display_name: "Steve Jobs", archetype: "The Product Visionary" },
  { agent_id: "agt_003", display_name: "Sun Tzu", archetype: "The Strategist" },
  { agent_id: "agt_004", display_name: "Napoleon", archetype: "The Commander" },
  { agent_id: "agt_005", display_name: "Marcus Aurelius", archetype: "The Stoic" },
  { agent_id: "agt_006", display_name: "Cleopatra", archetype: "The Diplomat" },
  { agent_id: "agt_007", display_name: "Leonardo da Vinci", archetype: "The Polymath" },
  { agent_id: "agt_008", display_name: "Ada Lovelace", archetype: "The Computational Pioneer" },
  { agent_id: "agt_009", display_name: "Marie Curie", archetype: "The Scientist" },
  { agent_id: "agt_010", display_name: "Jorge Luis Borges", archetype: "The Literary Labyrinth" },
  { agent_id: "agt_011", display_name: "Leon Trotsky", archetype: "The Revolutionary" },
  { agent_id: "agt_012", display_name: "Friedrich Nietzsche", archetype: "The Iconoclast" },
  { agent_id: "agt_013", display_name: "Nikola Tesla", archetype: "The Futurist Engineer" },
  { agent_id: "agt_014", display_name: "Marie Antoinette", archetype: "The Court Symbolist" },
  { agent_id: "agt_015", display_name: "Frida Kahlo", archetype: "The Identity Artist" },
  { agent_id: "agt_016", display_name: "Salvador Dali", archetype: "The Surrealist" },
] as const;

export default legendCatalog;