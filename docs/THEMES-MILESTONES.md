# Dynamic themes: milestones and gates

Classic remains the default until the M5 QA gate passes. Only one shell engine
and one notification server may run at a time. The dynamic reference pack is a
format example, not one of the six finished themes.

| Milestone | Scope | Acceptance gate |
| --- | --- | --- |
| M1 | Engine and runtime (Part 2) | Start the dynamic shell and load validated tokens; switching and rollback are verified on a live session. |
| M2 | Shared surfaces (Parts 3 and 4) | Required surfaces and service adapters run, support keyboard access, and pass their live and automated tests. |
| M3 | Six themes (Part 5) | Each pack passes validation and its screenshot-parity checklist; no theme counts as done until that checklist is complete. |
| M4 | System integration and sounds (Part 6) | Compositor, applications, wallpapers and generated sounds apply and roll back together; assets satisfy the legal policy. |
| M5 | Settings, installer, QA (Part 7) | Settings and installer flows, accessibility, upgrade, rollback and live QA pass; only then reconsider the default engine. |

Live compositor and shell behaviour cannot be established by offline tests alone.
Track unresolved integration claims in `docs/UNVERIFIED.md` and do not promote a
milestone based only on the presence of a skeleton.
