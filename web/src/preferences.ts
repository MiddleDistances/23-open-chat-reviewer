import { useEffect, useState } from "react";

export type ExperienceMode = "basic" | "advanced";

const STORAGE_KEY = "open-chat-reviewer.experience-mode";
const CHANGE_EVENT = "open-chat-reviewer:experience-mode";

export function readExperienceMode(): ExperienceMode {
  if (typeof window === "undefined") return "basic";
  return window.localStorage.getItem(STORAGE_KEY) === "advanced" ? "advanced" : "basic";
}

export function saveExperienceMode(mode: ExperienceMode): void {
  window.localStorage.setItem(STORAGE_KEY, mode);
  window.dispatchEvent(new CustomEvent<ExperienceMode>(CHANGE_EVENT, { detail: mode }));
}

export function useExperienceMode(): [ExperienceMode, (mode: ExperienceMode) => void] {
  const [mode, setMode] = useState<ExperienceMode>(readExperienceMode);

  useEffect(() => {
    const handleChange = (event: Event) => {
      const selected = (event as CustomEvent<ExperienceMode>).detail;
      setMode(selected === "advanced" ? "advanced" : "basic");
    };
    const handleStorage = () => setMode(readExperienceMode());
    window.addEventListener(CHANGE_EVENT, handleChange);
    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener(CHANGE_EVENT, handleChange);
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  return [mode, saveExperienceMode];
}
