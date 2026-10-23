import type { Bootstrap } from "@starshop/shared";
import { createContext, useContext } from "react";

export const BootContext = createContext<Bootstrap | null>(null);

export function useBoot(): Bootstrap {
  const value = useContext(BootContext);
  if (!value) throw new Error("useBoot outside of BootContext");
  return value;
}
