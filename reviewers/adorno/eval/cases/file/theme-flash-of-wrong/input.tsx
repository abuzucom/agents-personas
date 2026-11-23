import { useEffect, useState } from "react";

type Theme = "light" | "dark";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const stored = window.localStorage.getItem("app-theme");
    if (stored === "dark" || stored === "light") {
      setTheme(stored);
      document.documentElement.dataset.theme = stored;
    }
  }, []);

  return (
    <div data-theme={theme} className="app-shell">
      <header>
        <button
          onClick={() => {
            const next: Theme = theme === "light" ? "dark" : "light";
            setTheme(next);
            document.documentElement.dataset.theme = next;
            window.localStorage.setItem("app-theme", next);
          }}
        >
          Toggle theme
        </button>
      </header>
      <main>{children}</main>
    </div>
  );
}
