# Part 1 progress — strategy and Theme Packs

- [ ] Task 1: engine decision, safe switching and doctor
- [x] Task 2: Theme Pack format and schemas (existing implementation; schema and archive tests pass)
- [x] Task 3: repository layout (existing implementation; layout tests pass)
- [ ] Task 4: iarch-theme commands and transactional apply
- [x] Task 5: state, overrides and status records (existing implementation; record and drift tests pass)
- [x] Task 6: asset and legal policy (existing document and notices checks pass)
- [x] Task 7: milestones and gates (existing document and status drift check pass)
- [x] Task 8: tests and repository gates (2,470 Python tests, eight skipped; see report)
- [ ] Acceptance review and Part 1 report — updated report records remaining partial items; do not treat these as complete.

Tasks 1 and 4 remain partial. The normal shell-switch CLI now uses the
journalled notification handoff and recovery, but the older programmatic switch
and rollback functions are not yet migrated. The common lock covers the main
apply and switch entry points. A generic crash-recoverable step runner now exists
with fault-injection tests, but Classic and Dynamic apply are not wired to it;
cross-engine apply coordination and real recovery handlers remain to be implemented
and tested. The Dynamic feature flag defaults false, and the separate unfinished
shell guard remains in place. Do not tick a partial task.
