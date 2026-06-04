import { create } from "zustand";

import type { MaterialCatalog, WallCheckResult } from "@/lib/api";

interface CheckState {
  catalog: MaterialCatalog | null;
  result: WallCheckResult | null;
  catalogLoading: boolean;
  checking: boolean;
  errorMessage: string | null;
  setCatalog: (catalog: MaterialCatalog) => void;
  setCatalogLoading: (catalogLoading: boolean) => void;
  setChecking: (checking: boolean) => void;
  setResult: (result: WallCheckResult | null) => void;
  setErrorMessage: (errorMessage: string | null) => void;
}

export const useCheckStore = create<CheckState>((set) => ({
  catalog: null,
  result: null,
  catalogLoading: false,
  checking: false,
  errorMessage: null,
  setCatalog: (catalog) => set({ catalog }),
  setCatalogLoading: (catalogLoading) => set({ catalogLoading }),
  setChecking: (checking) => set({ checking }),
  setResult: (result) => set({ result }),
  setErrorMessage: (errorMessage) => set({ errorMessage }),
}));
