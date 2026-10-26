"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";

const THEME_KEY = "moseori_user_theme";
type Theme = "light" | "dark";
type ThemePreference = Theme | "system";
const ThemeContext = createContext({ theme: "light" as Theme, preference: "system" as ThemePreference, toggleTheme: () => {}, setTheme: (_value: ThemePreference) => {} });

export function UserTheme({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [theme, setTheme] = useState<Theme | null>(null);
  const [preference, setPreference] = useState<ThemePreference>("system");

  useEffect(() => {
    const system = window.matchMedia("(prefers-color-scheme: dark)");
    const read = () => {
      let saved: string | null = null;
      try { saved = localStorage.getItem(THEME_KEY) ?? localStorage.getItem("chat-kit-studio-theme"); } catch { /* Use system preference when storage is unavailable. */ }
      setTheme(saved === "light" || saved === "dark" ? saved : system.matches ? "dark" : "light");
      setPreference(saved === "light" || saved === "dark" ? saved : "system");
    };
    const storage = (event: StorageEvent) => { if (event.key === THEME_KEY || event.key === null) read(); };
    read();
    system.addEventListener("change", read);
    window.addEventListener("storage", storage);
    return () => { system.removeEventListener("change", read); window.removeEventListener("storage", storage); };
  }, []);

  function chooseTheme(next: ThemePreference) {
    setPreference(next);
    setTheme(next === "system" ? window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light" : next);
    try { localStorage.setItem(THEME_KEY, next); } catch { /* Theme still works for this session. */ }
  }
  function toggleTheme() { chooseTheme(theme === "dark" ? "light" : "dark"); }

  // Studio and account screens own their semantic surfaces and share the preference.
  const ownsSurface = pathname === "/studio" || pathname.startsWith("/studio/") || pathname === "/account" || pathname.startsWith("/account/") || pathname.startsWith("/dev/design-v10") || pathname.startsWith("/chats/");
  return <ThemeContext.Provider value={{ theme: theme ?? "light", preference, toggleTheme, setTheme: chooseTheme }}>
    {ownsSurface ? children : <div className="user-surface" data-user-theme={theme ?? "system"}>{children}</div>}
  </ThemeContext.Provider>;
}

export const useUserTheme = () => useContext(ThemeContext);
