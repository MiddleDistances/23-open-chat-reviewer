# UI action and feedback rules

Setup controls must make their real effect visible. These rules apply to every button
that starts work, checks external state, opens another surface, or changes setup scope.

1. Give the control a stable semantic `data-action-id` using dotted names such as
   `setup.machine.refresh` or `summary.run.start`. The HTML `id` is a stable kebab-case
   equivalent for browser automation and support instructions.
2. Name the real scope. Use **Check shared archive**, not **Discover**, when the action
   queries PostgreSQL. Never imply a network scan when none occurs.
3. An asynchronous action must immediately show a pending label, disable duplicate
   submission, and publish a `role="status"` message carrying the same `data-action-id`.
4. Completion must replace the pending message with a concrete success or error message.
   Errors use `role="alert"`; raw credentials, command output, and archive payloads never
   enter browser feedback.
5. Long-running work has one authoritative status surface and is polled from persisted
   job/database state. The button label is not the only progress indicator.
6. Navigation controls must navigate. Setup step buttons scroll to the selected section;
   they do not merely change colour.
7. Avoid duplicate actions. One setup guide entry is enough; machine-specific guidance
   belongs inside the **Add another machine** flow.

## Machine registration

Open Chat Reviewer does not scan the LAN or tailnet for computers. Each remote writer is
configured on that computer and registers itself by completing its first sync into the
shared PostgreSQL archive. `GET /api/setup/machines` reads that registry and returns
`method: "shared_database"` and `network_scan: false` so the UI can explain the behavior
without guessing.
