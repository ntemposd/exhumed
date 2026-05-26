// Topic editor concerns are intentionally isolated here: hydration from local
// storage, autosizing, and persistence of the current draft.
import { useEffect, useLayoutEffect, useRef, useState } from "react";

type UseTopicEditorStateOptions = {
  storageKey: string;
  defaultTopic: string;
};

export function useTopicEditorState({ storageKey, defaultTopic }: UseTopicEditorStateOptions) {
  const [topic, setTopic] = useState("");
  const [hasHydratedTopic, setHasHydratedTopic] = useState(false);
  const topicEditorRef = useRef<HTMLTextAreaElement | null>(null);

  useLayoutEffect(() => {
    const storedTopic = window.localStorage.getItem(storageKey);
    setTopic(storedTopic || defaultTopic);
    setHasHydratedTopic(true);
  }, [defaultTopic, storageKey]);

  useLayoutEffect(() => {
    const textarea = topicEditorRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "0px";
    textarea.style.height = `${textarea.scrollHeight + 8}px`;
  }, [topic]);

  useEffect(() => {
    if (!hasHydratedTopic) {
      return;
    }

    window.localStorage.setItem(storageKey, topic);
  }, [hasHydratedTopic, storageKey, topic]);

  return {
    topic,
    setTopic,
    topicEditorRef,
    hasHydratedTopic,
  };
}