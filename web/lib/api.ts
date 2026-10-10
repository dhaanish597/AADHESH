import { readSession } from "@/lib/auth";

/**
 * The console's one way of talking to Aadesh.
 *
 * Two deployment shapes are supported by the same code, and the difference is one environment
 * variable:
 *
 *   * **Local** (`make web` + `make api`): `NEXT_PUBLIC_API_BASE_URL` is unset, requests go to
 *     `/api/...` on the frontend's own origin, and `next.config.mjs` proxies them to the local
 *     JSON API. There is no identity provider, so no Authorization header is attached.
 *   * **Deployed** (static export on Amplify): `NEXT_PUBLIC_API_BASE_URL` is the API Gateway
 *     base URL, so requests are absolute and cross-origin -- which is why API Gateway carries a
 *     CORS policy naming this console's origin, and why the browser must see the ID token
 *     attached.
 *
 * A `401` announces itself rather than redirecting. Silently navigating away from the page the
 * user asked for is the behaviour that makes a console feel broken, and on the landing page --
 * which fetches one protected panel alongside two public ones -- it would bounce a visitor to a
 * login screen they did not ask for. Instead the header listens for `aadesh:unauthorized` and
 * offers sign-in, and the screen shows the message it already knows how to show.
 */

const BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

/**: Announced on `window` when the API refuses a request for want of a valid session. */
export const UNAUTHORIZED_EVENT = "aadesh:unauthorized";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** A failed call, described for the screen that has to render it. */
export type ApiFailure = {
  message: string;
  /** True only when the API never answered -- the one case where "is it running?" is the question. */
  unreachable: boolean;
};

/**
 * Whether the API failed to answer at all, as opposed to answering and refusing.
 *
 * The distinction decides what a screen is allowed to say. `fetch` rejects with a `TypeError`
 * when the request never reached the API; everything the API itself refuses arrives as an
 * `ApiError` carrying the status it refused with. A `401` is therefore a RUNNING API asking for a
 * session, and answering it with "start the API with `make api`" is false twice over: it names a
 * local server that has nothing to do with the deployed console, and it buries the sign-in the
 * header already offers. That is what a signed-out visitor to `/site` or `/supervisor` used to
 * read, directly beside the accurate "this screen needs a signed-in session".
 */
export function isUnreachable(error: unknown): boolean {
  return !(error instanceof ApiError);
}

/** A caught error, split into what to show and whether to blame the network. */
export function failureOf(error: unknown): ApiFailure {
  return {
    message: error instanceof Error ? error.message : String(error),
    unreachable: isUnreachable(error),
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const session = readSession();
  const headers = new Headers(init?.headers);
  if (session?.idToken) headers.set("Authorization", `Bearer ${session.idToken}`);

  const res = await fetch(`${BASE_URL}${path}`, { cache: "no-store", ...init, headers });

  if (res.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
  }

  const text = await res.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const reason =
      body && typeof body === "object" && "reason" in body
        ? String((body as { reason: unknown }).reason)
        : res.statusText;
    if (res.status === 401) {
      throw new ApiError(
        "This screen needs a signed-in session. Use Sign in in the header.",
        401,
      );
    }
    throw new ApiError(reason || "Request failed", res.status);
  }
  return body as T;
}

export function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}
