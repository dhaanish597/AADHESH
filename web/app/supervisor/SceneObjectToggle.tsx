"use client";

import { useState } from "react";
import type { SceneObjectKey } from "@/components/OperationsWorkspace";

export function SceneObjectToggle({
  objects,
  selectedObject,
  setSelectedObject,
}: {
  objects: { key: SceneObjectKey; label: string }[];
  selectedObject: SceneObjectKey | null;
  setSelectedObject: (key: SceneObjectKey) => void;
}) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-xs text-accent underline underline-offset-4"
      >
        Open site object inspector
      </button>
    );
  }
  return (
    <div className="mt-4 border border-line bg-panelAlt p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="label">Site object inspector</span>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs text-faint"
        >
          Close
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {objects.map((obj) => (
          <button
            key={obj.key}
            type="button"
            onClick={() => setSelectedObject(obj.key)}
            className={`border rounded-full px-3 py-1 text-xs transition-colors ${
              selectedObject === obj.key
                ? "border-accent bg-accent/10 text-accent"
                : "border-line text-dim hover:text-ink"
            }`}
          >
            {obj.label}
          </button>
        ))}
      </div>
    </div>
  );
}
