import { Moon, Sun } from "lucide-react";

import { useTheme } from "../hooks/useTheme";

const OPTIONS = [
  { value: "light", label: "Light mode", icon: Sun },
  { value: "dark", label: "Dark mode", icon: Moon },
];

/** Sun = light mode, moon = dark mode. The active one is highlighted. */
export default function ThemeToggle({ floating }) {
  const [theme, setTheme] = useTheme();
  const control = (
    <div className="theme-switch" role="radiogroup" aria-label="Colour theme">
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          aria-label={label}
          title={label}
          className={theme === value ? "active" : ""}
          onClick={() => setTheme(value)}
        >
          <Icon size={16} aria-hidden />
        </button>
      ))}
    </div>
  );
  return floating ? <div style={{ position: "fixed", top: 12, right: 12, zIndex: 30 }}>{control}</div> : control;
}
