"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button, Panel } from "@/components/ui";
import { authConfigured, signIn } from "@/lib/auth";

/**
 * Sign-in, when there is an identity provider to sign in to.
 *
 * A local run has none, and this page says so instead of offering a button that cannot work.
 * On the deployed console it hands off to the hosted UI, which is where the pool's password
 * policy, its MFA setting and its verification emails actually live -- the console never sees a
 * password.
 */
export default function LoginPage() {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setError(params.get("error_description") ?? params.get("error"));
  }, []);

  return (
    <div className="experience-home" style={{ padding: "clamp(2rem, 6vw, 5rem) clamp(1.25rem, 6vw, 6rem)" }}>
      <Panel title="Sign in" subtitle="Identity is what the authorization boundary reasons about.">
        {authConfigured ? (
          <>
            <p>
              Signing in proves who you are to the API Gateway authorizer. Your role and your
              assigned site come from your Cognito attributes, not from anything this page sends,
              and the Cedar policy decides what that role may do.
            </p>
            {error ? <p role="alert">The identity provider reported: {error}</p> : null}
            <div className="hero-actions">
              <Button onClick={() => signIn()}>Continue to sign in</Button>
            </div>
          </>
        ) : (
          <>
            <p>
              This build has no identity provider configured, which is the correct state for a
              local run: the console on your machine talks to the local JSON API, which does not
              ask for a token.
            </p>
            <p>
              A deployed console sets <code>NEXT_PUBLIC_COGNITO_DOMAIN</code> and{" "}
              <code>NEXT_PUBLIC_COGNITO_CLIENT_ID</code> at build time, and this page becomes the
              sign-in hand-off.
            </p>
            <div className="hero-actions">
              <Link href="/">Back to the overview</Link>
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}
