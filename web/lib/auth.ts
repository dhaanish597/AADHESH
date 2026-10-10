/**
 * The console's session, against the Cognito hosted UI.
 *
 * Two things about this file are deliberate and worth stating.
 *
 * **It is optional by construction.** A local run (`make web` against `make api`) has no
 * identity provider, and must keep working with no login at all: `authConfigured` is false when
 * no pool is configured, `attachAuth` adds no header, and the API's local skin does not ask for
 * one. The deployed console points the same pages at API Gateway, where the authorizer DOES ask
 * -- and where the ID token below is the only thing that satisfies it.
 *
 * **The implicit flow is chosen for the shape of this app, not by default.** The console is a
 * static export on Amplify Hosting: there is no server-side component that could hold a client
 * secret or exchange an authorization code. `response_type=token` returns the ID token in the
 * URL fragment, which never reaches a server and never appears in a Referer header. The same ID
 * token the API Gateway authorizer validates is the one the console attaches.
 */

export type Session = {
  idToken: string;
  accessToken: string;
  /** Epoch milliseconds. Compared against the local clock, which is why it is stored, not inferred. */
  expiresAt: number;
  role: string | null;
  principalId: string | null;
  assignedSite: string | null;
};

const DOMAIN = process.env.NEXT_PUBLIC_COGNITO_DOMAIN ?? "";
const CLIENT_ID = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID ?? "";
const STORAGE_KEY = "aadesh.session";

/** False in a local run, where there is no identity provider and no login is expected. */
export const authConfigured = DOMAIN !== "" && CLIENT_ID !== "";

function base64UrlDecode(value: string): string {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  return atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
}

export function claimsOf(idToken: string): Record<string, unknown> {
  try {
    return JSON.parse(base64UrlDecode(idToken.split(".")[1])) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function sessionFromTokens(idToken: string, accessToken: string, expiresIn: number): Session {
  const claims = claimsOf(idToken);
  return {
    idToken,
    accessToken,
    // Sixty seconds of slack: a token that expires during a request is indistinguishable from a
    // rejected one at the API, and the extra redirect is cheaper than the failed call.
    expiresAt: Date.now() + Math.max(0, expiresIn - 60) * 1000,
    role: typeof claims["custom:role"] === "string" ? (claims["custom:role"] as string) : null,
    principalId:
      typeof claims["custom:principal_id"] === "string"
        ? (claims["custom:principal_id"] as string)
        : null,
    assignedSite:
      typeof claims["custom:assigned_site"] === "string"
        ? (claims["custom:assigned_site"] as string)
        : null,
  };
}

export function readSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    if (!session.idToken || session.expiresAt <= Date.now()) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

/** Where Cognito sends the user back to. Must be registered on the app client, exactly. */
export function redirectUri(): string {
  return `${window.location.origin}/auth/callback`;
}

export function authorizeUrl(): string {
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    response_type: "token",
    scope: "openid email profile",
    redirect_uri: redirectUri(),
  });
  return `${DOMAIN}/login?${params.toString()}`;
}

export function signIn(): void {
  if (typeof window === "undefined" || !authConfigured) return;
  window.location.assign(authorizeUrl());
}

export function signOut(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  if (!authConfigured) {
    window.location.assign("/");
    return;
  }
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    logout_uri: `${window.location.origin}/`,
  });
  window.location.assign(`${DOMAIN}/logout?${params.toString()}`);
}

/**
 * Turn the hosted UI's redirect into a stored session.
 *
 * The implicit flow puts the tokens in the fragment, so this reads `window.location.hash` --
 * the same mechanism the worker screen uses for a scanned Parchi, and the reason nothing here
 * needs a server. Any error the hosted UI reports (`?error=...` in the query) is returned so the
 * login screen can say what happened rather than showing an empty console.
 */
export function completeSignIn(): { session: Session | null; error: string | null } {
  if (typeof window === "undefined") return { session: null, error: null };
  const query = new URLSearchParams(window.location.search);
  const error = query.get("error_description") ?? query.get("error");
  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const idToken = fragment.get("id_token");
  if (!idToken) return { session: null, error };
  const session = sessionFromTokens(
    idToken,
    fragment.get("access_token") ?? "",
    Number(fragment.get("expires_in") ?? "3600"),
  );
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  return { session, error: null };
}
