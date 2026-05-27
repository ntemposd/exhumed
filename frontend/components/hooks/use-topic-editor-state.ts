import { useEffect, useState } from "react";

type UseTopicEditorStateOptions = {
  storageKey: string;
  defaultTopic: string;
};

export function useTopicEditorState({ storageKey, defaultTopic }: UseTopicEditorStateOptions) {
  const [topic, setTopic] = useState(() => {
    if (typeof window === "undefined") return defaultTopic;
    return window.localStorage.getItem(storageKey) || defaultTopic;
  });

  useEffect(() => {
    window.localStorage.setItem(storageKey, topic);
  }, [storageKey, topic]);

  return {
    topic,
    setTopic,
  };
}
