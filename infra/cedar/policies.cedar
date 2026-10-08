// Aadesh — authorization policy.
//
// These rules live OUTSIDE application code on purpose. The two `forbid` rules below are
// load-bearing product behaviour, not decoration: without them a supervisor could complete a
// worker's acknowledgement, and a facilitator asked for help would gain read access to the
// worker's record. Both would silently destroy the thing the parchi is supposed to prove.
//
// In Cedar, `forbid` always beats `permit`. The @id annotations are mapped to human sentences
// in denials.json so a denial can be shown to a user as a reason rather than a 403.

// ---------------------------------------------------------------------------
// Supervisor: scoped to their own site
//
// `assignedSite` is OPTIONAL on Principal, because a worker and a facilitator do not have
// one. Cedar's validator refuses an unguarded read of an optional attribute, so every rule
// below is guarded with `principal has assignedSite`. That guard is not ceremony: it means a
// principal claiming role "supervisor" with no site assignment matches nothing at all.
// ---------------------------------------------------------------------------

permit (
  principal,
  action == Aadesh::Action::"IssueHalt",
  resource
) when {
  principal.role == "supervisor"
  && principal has assignedSite
  && resource.siteId == principal.assignedSite
};

permit (
  principal,
  action == Aadesh::Action::"CreateStandingOrder",
  resource
) when {
  principal.role == "supervisor"
  && principal has assignedSite
  && resource.siteId == principal.assignedSite
};

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
// ---------------------------------------------------------------------------

permit (
  principal,
  action == Aadesh::Action::"AckParchi",
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
// Facilitator: may assist a claim the worker explicitly shared. Nothing more.
// ---------------------------------------------------------------------------

permit (
  principal,
  action == Aadesh::Action::"AssistClaim",
  resource
) when {
  principal.role == "facilitator" && resource.sharedForAssistance == true
};

// ---------------------------------------------------------------------------
// The two forbids. These are the demo.
// ---------------------------------------------------------------------------

// A halt record is incomplete until the people it displaced have confirmed it themselves.
// Neither party can finish alone.
@id("no-proxy-acknowledgement")
forbid (
  principal,
  action == Aadesh::Action::"AckParchi",
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
