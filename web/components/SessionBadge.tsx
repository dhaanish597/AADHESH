"use client";

import { useEffect, useState } from "react";

import { UNAUTHORIZED_EVENT } from "@/lib/api";
import { authConfigured, readSession, signIn, signOut, type Session } from "@/lib/auth";

/**
 * Who the console thinks you are, and the way out.
 *
 * The role shown here is read from the ID token's own claims -- the same values the API Gateway
 * authorizer validated and the same ones Cedar reasons about. It is a disclosure, never a
 * control: nothing in the console can change a role, and choosing one on screen would be the
 * flaw the whole identity design exists to prevent.
 */
export function SessionBadge() {
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    setSession(readSession());
    // A refused request is this component's cue to offer the way back in. `readSession` is
    // re-read rather than assumed, because an expired token is exactly the case that produced
    // the refusal.
    const onUnauthorized = () => setSession(readSession());
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  if (!authConfigured) return null;

  if (!session) {
    return (
      <button type="button" className="header-cta" onClick={() => signIn()}>
        Sign in <span aria-hidden="true">↗</span>
      </button>
    );
  }

  return (
    <span className="header-cta" style={{ gap: ".5rem" }}>
      {session.role ?? "authenticated"}
      {session.assignedSite ? <span className="dim-on-concrete">{session.assignedSite}</span> : null}
      <button type="button" onClick={() => signOut()} style={{ textDecoration: "underline" }}>
        Sign out
      </button>
    </span>
  );
}
