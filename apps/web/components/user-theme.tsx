"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";

const THEME_KEY = "moseori_user_theme";
type Theme = "light" | "dark";
const ThemeContext = createContext({ theme: "light" as Theme, toggleTheme: () => {} });

export function UserTheme({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    const system = window.matchMedia("(prefers-color-scheme: dark)");
    const read = () => {
      let saved: string | null = null;
      try { saved = localStorage.getItem(THEME_KEY); } catch { /* Use system preference when storage is unavailable. */ }
      setTheme(saved === "light" || saved === "dark" ? saved : system.matches ? "dark" : "light");
    };
    const storage = (event: StorageEvent) => { if (event.key === THEME_KEY || event.key === null) read(); };
    read();
    system.addEventListener("change", read);
    window.addEventListener("storage", storage);
    return () => { system.removeEventListener("change", read); window.removeEventListener("storage", storage); };
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch { /* Theme still works for this session. */ }
  }

  // Studio owns its layout and theme; user-facing tokens never wrap that route.
  if (pathname === "/studio" || pathname.startsWith("/studio/")) return children;
  return <ThemeContext.Provider value={{ theme: theme ?? "light", toggleTheme }}>
    <div className="user-surface" data-user-theme={theme ?? "system"}>{children}</div>
  </ThemeContext.Provider>;
}

export const useUserTheme = () => useContext(ThemeContext);
