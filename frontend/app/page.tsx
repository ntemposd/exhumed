"use client";

// ssr: false prevents Next.js from server-rendering the workbench with default
// state (empty topic, no agents, no session ID) that immediately diverges from
// the localStorage-hydrated client state — the root cause of CLS on load and
// refresh. The shell div holds the page background while the JS bundle loads.
import dynamic from "next/dynamic";

const ChatWorkbench = dynamic(
  () => import("@/components/chat-workbench").then((m) => ({ default: m.ChatWorkbench })),
  { ssr: false, loading: () => <div className="shell" /> },
);

export default function Home() {
  return <ChatWorkbench />;
}
