# Release acceptance checklist — Resource Queue Manager v1.0.0

**Maintainer checklist only — not GitHub Release notes.**
Do not merge PR #9 or publish `v1.0.0` while any required acceptance gate is unresolved.
The existing `v1.0.0-rc.2` tag is immutable; its working branch is kept for reference
until the stable version is published. Tests of the RC do **not** validate later
changes on the feature branch (notably generic entity supervision).

## Automated preflight (exact PR head commit)

- [x] At the preparation snapshot, core Python unit tests, Home Assistant
      integration tests, HACS and hassfest pass on the feature branch.
- [ ] Confirm all three workflows remain green for the **final** PR commit SHA.
- [ ] Verify manifest and HACS names are `Resource Queue Manager`, manifest
      version `1.0.0`, integration type `service`, and HA minimum 2026.11.0.
- [ ] Confirm `v1.0.0` GitHub tag/release does **not** already exist.
- [ ] Check README, translations, release notes and migration/rollback instructions
      reflect the actual feature branch.

## Manual acceptance on an isolated HA 2026.11+ test instance

**Use only safe test helpers or an uncritical test lamp.** Back up Home Assistant
(including `.storage` and automations) before any in-place migration.
Do not experiment on the production heating relays.

Create helpers `input_boolean.rqm_test_a` through `input_boolean.rqm_test_d`
(all `off`) and at least two separate queue entries. Note each
`config_entry_id` from the action selector. A supervised entity must not
belong to two different queues. Test only one strategy at a time with those
helpers, or create separate helpers for each queue.

### FIFO (capacity 1)

- [ ] `resume` makes the queue `ready` once supervised entities are `off`.
- [ ] Request A, B, C, D using unique `resource_id` and matching entity IDs.
      Expect **active A**, waiting **B, C, D**.
- [ ] Release A (`input_boolean.rqm_test_a` still `off`).
      Expect **active B**, waiting **C, D**.
- [ ] Verify no second active reservation is granted while capacity is 1.

### LIFO (capacity 1)

- [ ] Request A, B, C, D. Expect **active A**, waiting **D, C, B**.
- [ ] Release A. Expect **active D**, waiting **C, B**.
- [ ] Release D. Expect **active C**, waiting **B**.
- [ ] Verify LIFO never preempts an already-active booking.

### Priority FIFO (capacity 1)

- [ ] Configure `highest_first`. Request A with priority 1 (active),
      B=4, C=8, D=4. Expect **waiting C, B, D**.
- [ ] Release A: expect C next; release C: expect B before D (FIFO ties).
- [ ] Cancel/release all reservations **before** changing strategy options.
- [ ] Configure `lowest_first`, repeat: expect **waiting B, D, C**,
      with B granted after A.
- [ ] Ensure missing `strategy_data.priority`, invalid priorities and
      extra fields are rejected; FIFO and LIFO reject priority metadata.

### Generic native and helper entities

- [ ] After clearing any active/waiting bookings, supervise existing
      `input_number`, `input_text`, `number`, `text` entities and confirm
      they are selectable and can be requested/released while available.
- [ ] Verify a supervised `input_boolean` changed to `on` cannot be
      released until HA reports `off`. Confirm `light`/`switch`
      retain the same safety check.
- [ ] Confirm an unavailable or unknown generic entity blocks recovery and
      active release. A numeric/text value is **not** proof of physical shutdown.

### Multi-entry isolation, recovery and compatibility

- [ ] Verify `config_entry_id` targets the intended queue; actions without it
      are rejected when two or more queue entries are configured.
- [ ] Verify distinct queue entries have independent active/waiting/capacity,
      sensors and persistence, and cannot supervise the same entity.
- [ ] Reload/restart: each queue returns to `paused`, saved active/waiting and
      bindings survive; resume only after checking real supervised states.
- [ ] Turn ON a supervised ON/OFF entity **without** a reservation in the
      isolated test queue; verify `resume` refuses it. Restore OFF safely.
- [ ] Check action picker, four sensors per entry, labels and forms in French
      and English on mobile and desktop.

### Existing v0.4 users

- [ ] On a disposable **populated v0.4 backup**, verify upgrade preserves
      config entry ID, four legacy sensor unique IDs, active/waiting order and
      entity bindings; do not reset storage to hide a recovery error.
- [ ] Update all four action calls with the original `config_entry_id`
      **before** adding a second manager.
- [ ] Rehearse the documented rollback using the matching HA backup.
- [ ] Review any physical heating system against independent electrical and
      thermal safety protections; queue counts are not a certified limiter.

## Publication (only after all gates pass)

1. Review PR #9 and its final green checks, then mark ready and merge into `main`.
2. Verify `main` has `manifest.json` version `1.0.0`, the release notes,
   and the `.github/workflows/publish-v1.yml` manual-only workflow.
3. In **GitHub → Actions → Publish v1.0.0 (manual) → Run workflow**,
   choose `main`, enter the exact confirmation token `PUBLISH_V1_0_0`.
4. The workflow must pass preflight, Python/HA tests, HACS and hassfest before
   creating tag/release `v1.0.0`. Never create a duplicate release.
5. Verify `/releases/latest` resolves to `v1.0.0`, install the stable
   Marketplace version on a test installation and confirm basic actions.
6. Only then consider removing `release/v1.0.0-rc.2` and the feature branch;
   keep all published release tags and do not delete `main`.

**Release workflow is not triggered by a merge.** Its human-triggered action
is intentionally the final gate; no GitHub Release is created during PR prep.
