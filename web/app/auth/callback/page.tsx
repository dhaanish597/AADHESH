"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Loading, Panel } from "@/components/ui";
import { authConfigured, completeSignIn } from "@/lib/auth";

/**
 * Where the hosted UI returns the user.
 *
 * The tokens arrive in the URL FRAGMENT (`#id_token=...`), which is never sent to a server and
 * never lands in a Referer header -- the reason the implicit flow is acceptable for a console
 * that is a static export with no server of its own. This page's whole job is to move that
 * fragment into a session and get out of the way, replacing the history entry so the token is
 * not left sitting in the address bar.
 */
export default function AuthCallbackPage() {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authConfigured) {
      setError("No identity provider is configured in this build.");
      return;
    }
    const { session, error: reported } = completeSignIn();
    if (reported) {
      setError(reported);
      return;
    }
    if (!session) {
      setError("The identity provider returned no token.");
      return;
    }
    window.location.replace(session.role === "worker" ? "/worker" : "/supervisor");
  }, []);

  return (
    <div className="experience-home" style={{ padding: "clamp(2rem, 6vw, 5rem) clamp(1.25rem, 6vw, 6rem)" }}>
      <Panel title="Completing sign-in">
        {error ? (
          <>
            <p role="alert">{error}</p>
            <p>
              <Link href="/login">Try signing in again</Link>
            </p>
          </>
        ) : (
          <Loading label="Completing sign-in" />
        )}
      </Panel>
    </div>
  );
}
