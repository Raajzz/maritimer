import { Monitor, Moon, Sun } from "lucide-react";

import { useTheme } from "../hooks/useTheme";
import { Button } from "./ui";

const NEXT = { light: "dark", dark: "system", system: "light" };
const ICON = { light: Sun, dark: Moon, system: Monitor };
const LABEL = { light: "Light theme", dark: "Dark theme", system: "System theme" };

/** Cycles light → dark → system. */
export default function ThemeToggle({ floating }) {
  const [theme, setTheme] = useTheme();
  const button = (
    <Button
      variant="ghost"
      icon={ICON[theme]}
      aria-label={`${LABEL[theme]} (switch to ${LABEL[NEXT[theme]].toLowerCase()})`}
      title={`${LABEL[theme]} — click for ${LABEL[NEXT[theme]].toLowerCase()}`}
      onClick={() => setTheme(NEXT[theme])}
    />
  );
  return floating ? <div style={{ position: "fixed", top: 12, right: 12, zIndex: 30 }}>{button}</div> : button;
}
