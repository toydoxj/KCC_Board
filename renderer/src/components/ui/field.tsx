import * as React from "react";

import { cn } from "@/lib/utils";

interface FieldProps {
  label: string;
  error?: string;
  children: React.ReactNode;
}

export function Field({ label, error, children }: FieldProps) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium text-foreground">{label}</span>
      {children}
      {error ? <span className="text-xs font-medium text-destructive">{error}</span> : null}
    </label>
  );
}

export const inputClassName = cn(
  "h-10 w-full rounded-md border border-input bg-white px-3 text-sm text-foreground shadow-sm outline-none transition-colors",
  "focus:border-primary focus:ring-2 focus:ring-ring/20",
  "disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground",
);
