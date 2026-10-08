"""The minimal worker roster this workflow needs, and a loud note about what it is not.

A parchi needs to know WHICH workers a halt displaced. That is the whole requirement. So this
module holds a worker id, a label safe to show, and whether the person is currently on the
site's roster -- and nothing else.

**A roster is not an eligibility determination.** `RosterEntry.active` means "currently
rostered at this site", which is bookkeeping about who was working. It carries no judgment
about who is eligible for anything, and in particular:

  * worker count is not an entitlement multiplier
  * being on the roster is not a legal claim on any scheme
  * being off the roster is not a denial of one
  * employment duration, wage and any demographic attribute are absent, because Aadesh has
    no cited basis for reasoning about them

There is no verified monetary entitlement amount in the authoritative corpus. Nothing in this
module produces, scales or approximates one. If a future reader is tempted to add a `wage`
field "so we can estimate", the answer is no: an estimate is exactly the invented figure this
system refuses to produce.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RosterEntry:
    """One worker on one site's roster.

    Deliberately tiny. `display_name` is a label safe to put on a slip; it is not an
    identity document. There is no Aadhaar, phone, address or bank field, and adding one
    would breach the minimisation rule the QR design also depends on.

    `active` is roster bookkeeping -- "currently rostered at this site". It is NOT an
    eligibility judgment, and code must not read it as one.
    """

    worker_id: str
    display_name: str
    active: bool = True

    def __post_init__(self) -> None:
        if not self.worker_id.strip():
            raise ValueError("RosterEntry requires a non-empty worker_id")


@dataclass(frozen=True, slots=True)
class Roster:
    """The workers on one site's roster at a moment.

    **Membership here is not an eligibility determination**, and `active` is not either. See
    the module docstring: worker count is not an entitlement multiplier, and nothing in this
    class produces or approximates a monetary figure.

    `active_entries()` is what a halt displaces. Keeping the inactive entries in the object
    rather than filtering them out is intentional: "this person was on the roster but not
    active" is a fact worth being able to show, and silently dropping them would make the
    record look like they were never there.
    """

    site_id: str
    entries: tuple[RosterEntry, ...] = ()

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for entry in self.entries:
            if entry.worker_id in seen:
                raise ValueError(
                    f"Roster for {self.site_id} lists {entry.worker_id!r} twice. One worker "
                    f"gets one parchi; a duplicate would silently produce two."
                )
            seen.add(entry.worker_id)

    def active_entries(self) -> tuple[RosterEntry, ...]:
        """The workers a halt on this site actually displaces."""
        return tuple(e for e in self.entries if e.active)

    def entry(self, worker_id: str) -> RosterEntry | None:
        return next((e for e in self.entries if e.worker_id == worker_id), None)
