// Aadesh — authorization policy.
//
// These rules live OUTSIDE application code on purpose. The `forbid` rules below are
// load-bearing product behaviour, not decoration: without them a supervisor could complete a
// worker's acknowledgement, and a facilitator asked for help would gain read access to the
// worker's record. Both would silently destroy the thing the parchi is supposed to prove.
//
// In Cedar, `forbid` always beats `permit`. The @id annotations are mapped to human sentences
// in denials.json so a denial can be shown to a user as a reason rather than a 403.
//
// WHAT DOES *NOT* BELONG IN THIS FILE
// -----------------------------------
// Cedar answers "may this principal perform this action on this resource?". It does not
// answer legal or compliance questions, and it does not own the parchi state machine.
// `Parchi.state` is carried as an attribute so a decision can be reported alongside the state
// it was made in, but **no rule below reads it**. Whether PENDING_ACK may become
// ACKNOWLEDGED is decided in `aadesh_core.parchi`, where the transitions and their evidence
// live. An authorization layer that also enforced transitions would be a second state
// machine, and the two would eventually disagree.
//
// TIME
// ----
// Cedar core has no clock. Every action therefore declares a `now` (epoch seconds) in its
// request context, and the consent rules compare against it. Expiry and revocation are
// decided HERE, by policy, rather than being pre-computed in Python and passed in as a
// boolean — a rule that runs outside the policy set is a rule the policy audit cannot see.

// ---------------------------------------------------------------------------
// Supervisor: scoped to their own site
//
// `assignedSite` is OPTIONAL on Principal, because a worker and a facilitator do not have
// one. Cedar's validator refuses an unguarded read of an optional attribute, so every rule
// below is guarded with `principal has assignedSite`. That guard is not ceremony: it means a
// principal claiming role "supervisor" with no site assignment matches nothing at all.
//
// The three site actions are grouped in one rule so that "a supervisor is scoped to exactly
// one site" is stated once. Adding a fourth site action to the list is a visible change;
// adding one somewhere else would not be.
// ---------------------------------------------------------------------------

permit (
  principal,
  action in [
    Aadesh::Action::"IssueHalt",
    Aadesh::Action::"ViewSiteExecution",
    Aadesh::Action::"CreateStandingOrder"
  ],
  resource
) when {
  principal.role == "supervisor"
  && principal has assignedSite
  && resource.siteId == principal.assignedSite
};

// A supervisor may read parches at a site they supervise. Note what this does NOT grant:
// it is ViewParchi, not AcknowledgeOwnParchi, and the forbid below closes the second door
// regardless of who issued the halt.
permit (
  principal,
  action == Aadesh::Action::"ViewParchi",
  resource
) when {
  principal.role == "supervisor"
  && principal has assignedSite
  && resource.siteId == principal.assignedSite
};

// ---------------------------------------------------------------------------
// Worker: their own parchi, and only their own
//
// `resource.worker == principal` is ENTITY equality, not string comparison. The attribute is
// a reference to a Principal entity, so it cannot be satisfied by a caller inventing an id.
// ---------------------------------------------------------------------------

permit (
  principal,
  action == Aadesh::Action::"AcknowledgeOwnParchi",
  resource
) when {
  resource.worker == principal
};

permit (
  principal,
  action == Aadesh::Action::"ViewParchi",
  resource
) when {
  resource.worker == principal
};

// ---------------------------------------------------------------------------
// Facilitator: assistance the worker explicitly and currently consented to
//
// Five conditions, and each one closes a different way of getting in:
//
//   consentGranted          the worker opted in at all
//   facilitator == principal consent names a PERSON, not a role
//   !(has revokedAt)        the worker has not withdrawn it
//   grantedAt <= now        it has actually started
//   expiresAt > now         it has not lapsed
//
// The resource is a ClaimAssistanceContext, never a Parchi. That is deliberate: a
// facilitator has no resource on which to name an assist request unless a consent context
// exists, so "no consent" is enforced structurally as well as by condition.
// ---------------------------------------------------------------------------

permit (
  principal,
  action == Aadesh::Action::"AssistClaim",
  resource
) when {
  principal.role == "facilitator"
  && resource.consentGranted == true
  && resource.facilitator == principal
  && !(resource has revokedAt)
  && resource.grantedAt <= context.now
  && resource.expiresAt > context.now
};

// ---------------------------------------------------------------------------
// The explicit denies. These are the demo.
// ---------------------------------------------------------------------------

// A halt record is incomplete until the people it displaced have confirmed it themselves.
// Neither party can finish alone.
//
// Stated as a forbid rather than as the absence of a permit, because the failure it prevents
// is one where a permit WOULD otherwise exist: a supervisor is permitted ViewParchi for this
// very parchi. The boundary is between reading and confirming, so it has to be written as a
// subtraction from a granted set.
@id("no-proxy-acknowledgement")
forbid (
  principal,
  action == Aadesh::Action::"AcknowledgeOwnParchi",
  resource
) when {
  resource.worker != principal
};

// A facilitator reaches a shared claim through AssistClaim, which returns a REDACTED view.
// Opting in to help never becomes opting in to full disclosure.
@id("assist-is-not-disclosure")
forbid (
  principal,
  action == Aadesh::Action::"ViewParchi",
  resource
) when {
  principal.role == "facilitator"
};

// Assistance is only ever granted by a live consent. This forbid makes the negative case
// explicit and gives it a sentence a user can read, rather than leaving it to fall through
// to the generic "no policy permits that action" default.
@id("assist-requires-live-consent")
forbid (
  principal,
  action == Aadesh::Action::"AssistClaim",
  resource
) when {
  resource.consentGranted == false
  || resource has revokedAt
  || resource.grantedAt > context.now
  || resource.expiresAt <= context.now
};
