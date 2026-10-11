"use client";

import { useEffect } from "react";
import { authConfigured, readSession } from "@/lib/auth";

/** Keep the legacy site URL stable while routing it to the data-backed console. */
export default function SitePage() {
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    if (!authConfigured) {
      window.location.replace(query.get("demo") === "1" ? "/supervisor?demo=1" : "/supervisor");
      return;
    }
    const role = readSession()?.role;
    const destination = role === "worker"
      ? "/worker"
      : role === "facilitator"
        ? "/facilitator"
        : role === "supervisor"
          ? "/supervisor"
          : role
            ? "/login?error=workspace_unavailable"
            : "/login";
    window.location.replace(destination);
  }, []);
  return null;
}
