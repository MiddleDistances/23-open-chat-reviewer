# 23-open-chat-reviewer capabilities

*Created: 2026-10-15*

This consolidated capability inventory preserves dated atlas source audits and the selected reuse assessment update. It contains 7 capability families and 7 source variants.

The document preserves committed and experimental variants so a reviewer can find reusable work before it reaches the default branch. It is a discovery snapshot, not proof of current checkout contents, runtime success, deployment, ownership, or access. Each variant has a `source_audit` object retaining the original audit date, method, baseline, coverage, limitations, and central document provenance.

| Capability family | Variants | Maturity values |
| --- | ---: | --- |
| `opencode-sqlite-ingestion` | 1 | experimental |
| `compact-recall` | 1 | unknown |
| `incremental-source-checkpoints` | 1 | unknown |
| `recall-mcp` | 1 | experimental |
| `recall-skill-installer` | 1 | unknown |
| `shared-timesheet-evidence` | 1 | unknown |
| `versioned-token-costs` | 1 | unknown |

The `source_audit.document_path` values point into the atlas audit tree and are historical evidence references. A future owner-side update should run the audit skill against the selected commit or reviewed working tree, retain its own source receipts, and update this document before commit/PR review. No automatic hook or CI updater is implied by this file.

Reuse guidance for selected variants was assessed on 2026-10-15 using `canetoad-reuse/v1`. Each assessment scopes its intended use, work needed, effort estimate and acceptance condition. Source audit dates, historical variants, runtime and deployment evidence remain separate; other variants may still be unassessed or retain legacy hints.

<!-- canetoad-capabilities:v1 -->
```json
{
  "audit": {
    "baseline": null,
    "checked_at": "2026-10-26",
    "coverage": [
      {
        "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
        "ref": "refs/heads/codex/archive-storage",
        "remote_freshness": "not-applicable",
        "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
        "state": "partial"
      },
      {
        "commit_date": "2026-09-29T11:39:41+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/heads/codex/archive-storage",
        "remote_freshness": "not-applicable",
        "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/heads/codex/archive-storage",
        "remote_freshness": "not-applicable",
        "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-28T23:02:17+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/heads/codex/private-archive-compat",
        "remote_freshness": "not-applicable",
        "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/heads/codex/private-archive-compat",
        "remote_freshness": "not-applicable",
        "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-07T12:02:59+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/heads/codex/review-dependency-upgrades-20260907",
        "remote_freshness": "not-applicable",
        "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/heads/codex/review-dependency-upgrades-20260907",
        "remote_freshness": "not-applicable",
        "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
        "state": "skipped"
      },
      {
        "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
        "ref": "refs/heads/codex/token-cost-projection",
        "remote_freshness": "not-applicable",
        "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
        "state": "partial"
      },
      {
        "commit_date": "2026-09-07T12:51:46+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/heads/codex/token-cost-projection",
        "remote_freshness": "not-applicable",
        "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/heads/codex/token-cost-projection",
        "remote_freshness": "not-applicable",
        "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-28T23:14:16+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/heads/codex/worker-15min",
        "remote_freshness": "not-applicable",
        "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/heads/codex/worker-15min",
        "remote_freshness": "not-applicable",
        "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
        "state": "skipped"
      },
      {
        "reason": "Selected implementation/caller slices reviewed via helper receipts; entire branch remains unreviewed.",
        "ref": "refs/heads/docs/recall-skill-refresh-20261014",
        "remote_freshness": "not-applicable",
        "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
        "state": "partial"
      },
      {
        "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
        "ref": "refs/heads/docs/recall-skill-refresh-20261014",
        "remote_freshness": "not-applicable",
        "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
        "state": "partial"
      },
      {
        "commit_date": "2026-10-14T16:29:44+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/heads/docs/recall-skill-refresh-20261014",
        "remote_freshness": "not-applicable",
        "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/heads/docs/recall-skill-refresh-20261014",
        "remote_freshness": "not-applicable",
        "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
        "state": "skipped"
      },
      {
        "reason": "Selected implementation/caller slices reviewed via helper receipts; entire branch remains unreviewed.",
        "ref": "refs/heads/fix/bounded-refresh-health-20261013",
        "remote_freshness": "not-applicable",
        "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
        "state": "partial"
      },
      {
        "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
        "ref": "refs/heads/fix/bounded-refresh-health-20261013",
        "remote_freshness": "not-applicable",
        "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
        "state": "partial"
      },
      {
        "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
        "ref": "refs/heads/fix/bounded-refresh-health-20261013",
        "remote_freshness": "not-applicable",
        "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
        "state": "partial"
      },
      {
        "commit_date": "2026-10-13T21:18:00+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/heads/fix/bounded-refresh-health-20261013",
        "remote_freshness": "not-applicable",
        "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
        "state": "skipped"
      },
      {
        "commit_date": "2026-10-13T23:22:18+08:00",
        "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
        "ref": "refs/heads/fix/compact-recall-20261013",
        "remote_freshness": "not-applicable",
        "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
        "state": "partial"
      },
      {
        "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
        "ref": "refs/heads/fix/compact-recall-20261013",
        "remote_freshness": "not-applicable",
        "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
        "state": "partial"
      },
      {
        "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
        "ref": "refs/heads/fix/compact-recall-20261013",
        "remote_freshness": "not-applicable",
        "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
        "state": "partial"
      },
      {
        "commit_date": "2026-10-07T22:29:24+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/heads/fix/idle-database-churn-20261007",
        "remote_freshness": "not-applicable",
        "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/heads/fix/idle-database-churn-20261007",
        "remote_freshness": "not-applicable",
        "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
        "state": "skipped"
      },
      {
        "commit_date": "2026-10-14T16:34:40+08:00",
        "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
        "ref": "refs/heads/main",
        "remote_freshness": "not-applicable",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial"
      },
      {
        "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
        "ref": "refs/heads/main",
        "remote_freshness": "not-applicable",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial"
      },
      {
        "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
        "ref": "refs/heads/main",
        "remote_freshness": "not-applicable",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial"
      },
      {
        "commit_date": "2026-10-13T21:02:24+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/heads/maintenance/repo-health-20261013",
        "remote_freshness": "not-applicable",
        "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/heads/maintenance/repo-health-20261013",
        "remote_freshness": "not-applicable",
        "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
        "state": "skipped"
      },
      {
        "commit_date": "2026-10-14T16:34:40+08:00",
        "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
        "ref": "refs/remotes/origin/HEAD",
        "remote_freshness": "unknown",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial"
      },
      {
        "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
        "ref": "refs/remotes/origin/HEAD",
        "remote_freshness": "unknown",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial"
      },
      {
        "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
        "ref": "refs/remotes/origin/HEAD",
        "remote_freshness": "unknown",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial"
      },
      {
        "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
        "ref": "refs/remotes/origin/codex/archive-storage",
        "remote_freshness": "unknown",
        "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
        "state": "partial"
      },
      {
        "commit_date": "2026-09-29T11:39:41+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/codex/archive-storage",
        "remote_freshness": "unknown",
        "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/codex/archive-storage",
        "remote_freshness": "unknown",
        "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-28T23:02:17+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/codex/private-archive-compat",
        "remote_freshness": "unknown",
        "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/codex/private-archive-compat",
        "remote_freshness": "unknown",
        "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-07T12:02:59+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/codex/review-dependency-upgrades-20260907",
        "remote_freshness": "unknown",
        "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/codex/review-dependency-upgrades-20260907",
        "remote_freshness": "unknown",
        "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
        "state": "skipped"
      },
      {
        "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
        "ref": "refs/remotes/origin/codex/token-cost-projection",
        "remote_freshness": "unknown",
        "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
        "state": "partial"
      },
      {
        "commit_date": "2026-09-07T12:51:46+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/codex/token-cost-projection",
        "remote_freshness": "unknown",
        "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/codex/token-cost-projection",
        "remote_freshness": "unknown",
        "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-28T23:14:16+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/codex/worker-15min",
        "remote_freshness": "unknown",
        "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/codex/worker-15min",
        "remote_freshness": "unknown",
        "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-07T04:07:39Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/bun/web/jsdom-30.0.1",
        "remote_freshness": "unknown",
        "revision": "8c1dadc2aeeef60022a346ed77aae12e450040fb",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/bun/web/jsdom-30.0.1",
        "remote_freshness": "unknown",
        "revision": "8c1dadc2aeeef60022a346ed77aae12e450040fb",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-07T04:07:35Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/bun/web/testing-library/jest-dom-7.0.1",
        "remote_freshness": "unknown",
        "revision": "141efe84ae5068dec98d28a7427458e8c4468228",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/bun/web/testing-library/jest-dom-7.0.1",
        "remote_freshness": "unknown",
        "revision": "141efe84ae5068dec98d28a7427458e8c4468228",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-27T19:18:30Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-13a777b093",
        "remote_freshness": "unknown",
        "revision": "11a5e5c62412875a4c20b1bb3b02ca50651ff407",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-13a777b093",
        "remote_freshness": "unknown",
        "revision": "11a5e5c62412875a4c20b1bb3b02ca50651ff407",
        "state": "skipped"
      },
      {
        "commit_date": "2026-10-11T19:19:48Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-3457e10658",
        "remote_freshness": "unknown",
        "revision": "796791c5604f660dd02281709f958746974330d1",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-3457e10658",
        "remote_freshness": "unknown",
        "revision": "796791c5604f660dd02281709f958746974330d1",
        "state": "skipped"
      },
      {
        "commit_date": "2026-10-04T19:33:06Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/github_actions/actions-03db81fe05",
        "remote_freshness": "unknown",
        "revision": "661b22c4b41ddefd10386d5ada86a6ece7c6d4a2",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/github_actions/actions-03db81fe05",
        "remote_freshness": "unknown",
        "revision": "661b22c4b41ddefd10386d5ada86a6ece7c6d4a2",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-03T04:00:09Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/github_actions/actions-2514a98571",
        "remote_freshness": "unknown",
        "revision": "cf7a89c7c7231e5f57e03c2437fcf7dd14501828",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/github_actions/actions-2514a98571",
        "remote_freshness": "unknown",
        "revision": "cf7a89c7c7231e5f57e03c2437fcf7dd14501828",
        "state": "skipped"
      },
      {
        "commit_date": "2026-08-30T01:04:00Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/jsdom-30.0.1",
        "remote_freshness": "unknown",
        "revision": "2024029bd0939a2f7bf1b2edf7d1a181b2a1314f",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/jsdom-30.0.1",
        "remote_freshness": "unknown",
        "revision": "2024029bd0939a2f7bf1b2edf7d1a181b2a1314f",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-03T04:01:27Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/lucide-react-1.37.0",
        "remote_freshness": "unknown",
        "revision": "e905acafa5bcaedcdf9dbe539879b37ea2023edb",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/lucide-react-1.37.0",
        "remote_freshness": "unknown",
        "revision": "e905acafa5bcaedcdf9dbe539879b37ea2023edb",
        "state": "skipped"
      },
      {
        "commit_date": "2026-08-30T01:03:54Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/testing-library/jest-dom-7.0.1",
        "remote_freshness": "unknown",
        "revision": "e1c3295c90021cd73c513e4ffe076a6986bbf253",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/testing-library/jest-dom-7.0.1",
        "remote_freshness": "unknown",
        "revision": "e1c3295c90021cd73c513e4ffe076a6986bbf253",
        "state": "skipped"
      },
      {
        "commit_date": "2026-08-30T01:03:52Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vite-8.2.2",
        "remote_freshness": "unknown",
        "revision": "2bade23ace71fb47b7273185466aedc317b82966",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vite-8.2.2",
        "remote_freshness": "unknown",
        "revision": "2bade23ace71fb47b7273185466aedc317b82966",
        "state": "skipped"
      },
      {
        "commit_date": "2026-08-30T01:04:03Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vitest-4.1.11",
        "remote_freshness": "unknown",
        "revision": "f743dafa78068d7006d95e39d690d3edbfcad23e",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vitest-4.1.11",
        "remote_freshness": "unknown",
        "revision": "f743dafa78068d7006d95e39d690d3edbfcad23e",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-13T19:04:49Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/pip/mcp-gte-1.12-and-lt-3",
        "remote_freshness": "unknown",
        "revision": "934cb7738cf8bf49fc6e1317dcabdafdb1452418",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/pip/mcp-gte-1.12-and-lt-3",
        "remote_freshness": "unknown",
        "revision": "934cb7738cf8bf49fc6e1317dcabdafdb1452418",
        "state": "skipped"
      },
      {
        "commit_date": "2026-08-30T01:03:40Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/pip/uv-build-gte-0.8.0-and-lt-0.13",
        "remote_freshness": "unknown",
        "revision": "760b245daa7e818200b3c508849323fa86390351",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/pip/uv-build-gte-0.8.0-and-lt-0.13",
        "remote_freshness": "unknown",
        "revision": "760b245daa7e818200b3c508849323fa86390351",
        "state": "skipped"
      },
      {
        "commit_date": "2026-10-02T06:33:12Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/dependabot/uv/pyjwt-2.15.0",
        "remote_freshness": "unknown",
        "revision": "e1db24b75800eef8040e797071c550c9c1bf3842",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/dependabot/uv/pyjwt-2.15.0",
        "remote_freshness": "unknown",
        "revision": "e1db24b75800eef8040e797071c550c9c1bf3842",
        "state": "skipped"
      },
      {
        "reason": "Selected implementation/caller slices reviewed via helper receipts; entire branch remains unreviewed.",
        "ref": "refs/remotes/origin/docs/recall-skill-refresh-20261014",
        "remote_freshness": "unknown",
        "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
        "state": "partial"
      },
      {
        "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
        "ref": "refs/remotes/origin/docs/recall-skill-refresh-20261014",
        "remote_freshness": "unknown",
        "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
        "state": "partial"
      },
      {
        "commit_date": "2026-10-14T16:29:44+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/docs/recall-skill-refresh-20261014",
        "remote_freshness": "unknown",
        "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/docs/recall-skill-refresh-20261014",
        "remote_freshness": "unknown",
        "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
        "state": "skipped"
      },
      {
        "reason": "Selected implementation/caller slices reviewed via helper receipts; entire branch remains unreviewed.",
        "ref": "refs/remotes/origin/fix/bounded-refresh-health-20261013",
        "remote_freshness": "unknown",
        "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
        "state": "partial"
      },
      {
        "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
        "ref": "refs/remotes/origin/fix/bounded-refresh-health-20261013",
        "remote_freshness": "unknown",
        "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
        "state": "partial"
      },
      {
        "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
        "ref": "refs/remotes/origin/fix/bounded-refresh-health-20261013",
        "remote_freshness": "unknown",
        "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
        "state": "partial"
      },
      {
        "commit_date": "2026-10-13T21:18:00+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/fix/bounded-refresh-health-20261013",
        "remote_freshness": "unknown",
        "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
        "state": "skipped"
      },
      {
        "commit_date": "2026-10-13T23:22:18+08:00",
        "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
        "ref": "refs/remotes/origin/fix/compact-recall-20261013",
        "remote_freshness": "unknown",
        "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
        "state": "partial"
      },
      {
        "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
        "ref": "refs/remotes/origin/fix/compact-recall-20261013",
        "remote_freshness": "unknown",
        "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
        "state": "partial"
      },
      {
        "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
        "ref": "refs/remotes/origin/fix/compact-recall-20261013",
        "remote_freshness": "unknown",
        "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
        "state": "partial"
      },
      {
        "commit_date": "2026-10-14T16:34:40+08:00",
        "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
        "ref": "refs/remotes/origin/main",
        "remote_freshness": "unknown",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial"
      },
      {
        "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
        "ref": "refs/remotes/origin/main",
        "remote_freshness": "unknown",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial"
      },
      {
        "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
        "ref": "refs/remotes/origin/main",
        "remote_freshness": "unknown",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial"
      },
      {
        "commit_date": "2026-10-13T21:02:24+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/maintenance/repo-health-20261013",
        "remote_freshness": "unknown",
        "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/maintenance/repo-health-20261013",
        "remote_freshness": "unknown",
        "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-06T19:17:55Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/review-20",
        "remote_freshness": "unknown",
        "revision": "88f3ebe08f08a70575208ef6b72bd6289bcc6f4d",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/review-20",
        "remote_freshness": "unknown",
        "revision": "88f3ebe08f08a70575208ef6b72bd6289bcc6f4d",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-06T19:18:04Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/review-21",
        "remote_freshness": "unknown",
        "revision": "757a81942bc46b50655584b0553fad7cdc418db1",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/review-21",
        "remote_freshness": "unknown",
        "revision": "757a81942bc46b50655584b0553fad7cdc418db1",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-06T19:18:32Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/review-22",
        "remote_freshness": "unknown",
        "revision": "b2f4a2b9afc264ec4b3a884edd5ec7e25fcf15b3",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/review-22",
        "remote_freshness": "unknown",
        "revision": "b2f4a2b9afc264ec4b3a884edd5ec7e25fcf15b3",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-06T19:18:40Z",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/review-23",
        "remote_freshness": "unknown",
        "revision": "18059bd59bb7833af6ab09b4a8218f5f2f08a3ac",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/review-23",
        "remote_freshness": "unknown",
        "revision": "18059bd59bb7833af6ab09b4a8218f5f2f08a3ac",
        "state": "skipped"
      },
      {
        "commit_date": "2026-09-07T11:31:18+08:00",
        "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
        "ref": "refs/remotes/origin/review-9",
        "remote_freshness": "unknown",
        "revision": "35f2eefc639da6e2075d2e7cadd8f84f8d360177",
        "state": "skipped"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/remotes/origin/review-9",
        "remote_freshness": "unknown",
        "revision": "35f2eefc639da6e2075d2e7cadd8f84f8d360177",
        "state": "skipped"
      },
      {
        "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
        "ref": "refs/tags/recall-skill-20261014",
        "remote_freshness": "not-applicable",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial"
      },
      {
        "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
        "ref": "refs/tags/recall-skill-20261014",
        "remote_freshness": "not-applicable",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial"
      },
      {
        "reason": "Inventoried only; source inspection pending.",
        "ref": "refs/tags/v0.1.0-alpha.1",
        "remote_freshness": "not-applicable",
        "revision": "b027ccae1c42a87bbf5b81e1a4280de7e81ba77f",
        "state": "skipped"
      },
      {
        "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
        "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/archive-storage/23-open-chat-reviewer",
        "remote_freshness": "not-applicable",
        "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
        "state": "skipped"
      },
      {
        "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
        "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/archive-storage/23-open-chat-reviewer",
        "remote_freshness": "not-applicable",
        "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
        "state": "skipped"
      },
      {
        "reason": "Location/HEAD inventoried; working files excluded.",
        "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/archive-storage/23-open-chat-reviewer",
        "remote_freshness": "not-applicable",
        "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
        "state": "skipped"
      },
      {
        "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
        "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/public-chatreview-deploy/23-open-chat-reviewer",
        "remote_freshness": "not-applicable",
        "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
        "state": "skipped"
      },
      {
        "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
        "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/public-chatreview-deploy/23-open-chat-reviewer",
        "remote_freshness": "not-applicable",
        "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
        "state": "skipped"
      },
      {
        "reason": "Location/HEAD inventoried; working files excluded.",
        "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/public-chatreview-deploy/23-open-chat-reviewer",
        "remote_freshness": "not-applicable",
        "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
        "state": "skipped"
      },
      {
        "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
        "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer",
        "remote_freshness": "not-applicable",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "skipped"
      },
      {
        "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
        "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer",
        "remote_freshness": "not-applicable",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "skipped"
      },
      {
        "reason": "Location/HEAD inventoried; working files excluded.",
        "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer",
        "remote_freshness": "not-applicable",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "skipped"
      },
      {
        "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
        "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer-energy-fix",
        "remote_freshness": "not-applicable",
        "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
        "state": "skipped"
      },
      {
        "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
        "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer-energy-fix",
        "remote_freshness": "not-applicable",
        "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
        "state": "skipped"
      },
      {
        "reason": "Location/HEAD inventoried; working files excluded.",
        "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer-energy-fix",
        "remote_freshness": "not-applicable",
        "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
        "state": "skipped"
      },
      {
        "ref": "refs/heads/main + reviewed OpenCode working files",
        "revision": "7b0806823e749873803d350618609226e6fcbe04",
        "state": "partial",
        "remote_freshness": "observed",
        "reason": "Remote main matched HEAD before publication; inspected listed working files and their ingestion/configuration callers only."
      }
    ],
    "limitations": [
      "This owner document is a dated consolidation of prior atlas audits; it does not re-inspect the owner checkout.",
      "Committed and experimental source variants are retained separately. Presence here does not mean the variant exists at current HEAD, is merged, or is deployed.",
      "Runtime, deployment, current access, branch freshness, and compatibility were not re-established by this refresh.",
      "The atlas source-document paths and read receipts are historical atlas provenance; they are not assumed to be relative to the owner checkout.",
      "The 2026-10-26 review is limited to OpenCode ingestion and writer integration; earlier family source audit dates remain historical."
    ],
    "method": "Documentation-only refresh of a prior atlas consolidation. Restored each variant's original audit method, baseline, coverage, limitations, and central document provenance from the canonical catalogue; no source reinspection or owner execution.; bounded OpenCode working-source and caller review on 2026-10-26; previous family audits retained."
  },
  "capabilities": [
    {
      "id": "compact-recall",
      "kind": "interface",
      "name": "Cross-agent work recall",
      "purpose": "Find archived prior work and return bounded evidence/navigation for continued inspection.",
      "variants": [
        {
          "access": [
            "Read source at the recorded revision with git show <revision>:<path>.",
            "Runtime use requires the owner repository instructions, compatible environment and separately authorized data/service access; no access was established by this audit."
          ],
          "adoption_notes": [
            "Review this immutable entrypoint, relevant callers and dependency manifests before extracting an interface or comparing competing implementations.",
            "Do not infer a runnable combined pipeline from capabilities on different branches. Confirm contracts and current owner authority independently."
          ],
          "atlas_asset_id": "capability-23-open-chat-reviewer-compact-recall-7f8639b8dc35bfb6470c",
          "baseline_equivalence": "equivalent",
          "baseline_relation": "same-tip",
          "dependencies": [],
          "deployment": {
            "receipts": [],
            "status": "unknown"
          },
          "entrypoint_comparison": "identical-entrypoint-blob",
          "entrypoints": [
            "src/chatreview/recall.py (inspect implementation and owner command/contract before invocation)"
          ],
          "evidence": [
            {
              "kind": "code",
              "line": 1,
              "line_end": 10,
              "note": "Bounded source inspection; see source-reads.jsonl for receipt.",
              "path": "src/chatreview/recall.py",
              "revision": "7b0806823e749873803d350618609226e6fcbe04",
              "sha256": "351d135007350ce35bf85f0e2ff39cf47c3dfa57f9e130357d85e46661690d8d"
            },
            {
              "kind": "code",
              "line": 216,
              "line_end": 250,
              "note": "Bounded source inspection; see source-reads.jsonl for receipt.",
              "path": "src/chatreview/recall.py",
              "revision": "7b0806823e749873803d350618609226e6fcbe04",
              "sha256": "351d135007350ce35bf85f0e2ff39cf47c3dfa57f9e130357d85e46661690d8d"
            }
          ],
          "id": "commit-7b0806823e749873803d350618609226e6fcbe04",
          "inputs": [
            "Archive query and repository/source scope"
          ],
          "limitations": [
            "Archived text is historical and untrusted; operational claims require current corroboration.",
            "Only the cited source slices were inspected; callers, complete pipelines, saved experiment outcomes and operational readiness were not exhaustively reviewed.",
            "Dirty worktree contents were not inspected. Cached remote freshness, current access, deployment and runtime success are unknown."
          ],
          "maturity": "unknown",
          "maturity_evidence": "Current maintenance status was not established by bounded source inspection.",
          "outputs": [
            "Compact ranked historical work evidence"
          ],
          "runtime": {
            "receipts": [],
            "status": "not-checked"
          },
          "source": {
            "refs": [
              "refs/heads/main",
              "refs/remotes/origin/HEAD",
              "refs/remotes/origin/main"
            ],
            "revision": "7b0806823e749873803d350618609226e6fcbe04",
            "working_changes": null,
            "worktree": null
          },
          "source_audit": {
            "baseline": {
              "ref": "refs/remotes/origin/main",
              "revision": "7b0806823e749873803d350618609226e6fcbe04",
              "selection_evidence": "Locally cached origin default if available, otherwise conventional main/master or current HEAD; no fetch, not deployment evidence."
            },
            "checked_at": "2026-10-15",
            "coverage": [
              {
                "commit_date": "2026-09-29T11:39:41+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/codex/archive-storage",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-28T23:02:17+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/codex/private-archive-compat",
                "remote_freshness": "not-applicable",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T12:02:59+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "not-applicable",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T12:51:46+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/codex/token-cost-projection",
                "remote_freshness": "not-applicable",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-28T23:14:16+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/codex/worker-15min",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-14T16:29:44+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/docs/recall-skill-refresh-20261014",
                "remote_freshness": "not-applicable",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-13T21:18:00+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/fix/bounded-refresh-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-13T23:22:18+08:00",
                "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
                "ref": "refs/heads/fix/compact-recall-20261013",
                "remote_freshness": "not-applicable",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "commit_date": "2026-10-07T22:29:24+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/fix/idle-database-churn-20261007",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-14T16:34:40+08:00",
                "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
                "ref": "refs/heads/main",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "commit_date": "2026-10-13T21:02:24+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/maintenance/repo-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-14T16:34:40+08:00",
                "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
                "ref": "refs/remotes/origin/HEAD",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "commit_date": "2026-09-29T11:39:41+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/codex/archive-storage",
                "remote_freshness": "unknown",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-28T23:02:17+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/codex/private-archive-compat",
                "remote_freshness": "unknown",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T12:02:59+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "unknown",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T12:51:46+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/codex/token-cost-projection",
                "remote_freshness": "unknown",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-28T23:14:16+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/codex/worker-15min",
                "remote_freshness": "unknown",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T04:07:39Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/bun/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "8c1dadc2aeeef60022a346ed77aae12e450040fb",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T04:07:35Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/bun/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "141efe84ae5068dec98d28a7427458e8c4468228",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-27T19:18:30Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-13a777b093",
                "remote_freshness": "unknown",
                "revision": "11a5e5c62412875a4c20b1bb3b02ca50651ff407",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-11T19:19:48Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-3457e10658",
                "remote_freshness": "unknown",
                "revision": "796791c5604f660dd02281709f958746974330d1",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-04T19:33:06Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-03db81fe05",
                "remote_freshness": "unknown",
                "revision": "661b22c4b41ddefd10386d5ada86a6ece7c6d4a2",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-03T04:00:09Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-2514a98571",
                "remote_freshness": "unknown",
                "revision": "cf7a89c7c7231e5f57e03c2437fcf7dd14501828",
                "state": "skipped"
              },
              {
                "commit_date": "2026-08-30T01:04:00Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "2024029bd0939a2f7bf1b2edf7d1a181b2a1314f",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-03T04:01:27Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/lucide-react-1.37.0",
                "remote_freshness": "unknown",
                "revision": "e905acafa5bcaedcdf9dbe539879b37ea2023edb",
                "state": "skipped"
              },
              {
                "commit_date": "2026-08-30T01:03:54Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "e1c3295c90021cd73c513e4ffe076a6986bbf253",
                "state": "skipped"
              },
              {
                "commit_date": "2026-08-30T01:03:52Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vite-8.2.2",
                "remote_freshness": "unknown",
                "revision": "2bade23ace71fb47b7273185466aedc317b82966",
                "state": "skipped"
              },
              {
                "commit_date": "2026-08-30T01:04:03Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vitest-4.1.11",
                "remote_freshness": "unknown",
                "revision": "f743dafa78068d7006d95e39d690d3edbfcad23e",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-13T19:04:49Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/pip/mcp-gte-1.12-and-lt-3",
                "remote_freshness": "unknown",
                "revision": "934cb7738cf8bf49fc6e1317dcabdafdb1452418",
                "state": "skipped"
              },
              {
                "commit_date": "2026-08-30T01:03:40Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/pip/uv-build-gte-0.8.0-and-lt-0.13",
                "remote_freshness": "unknown",
                "revision": "760b245daa7e818200b3c508849323fa86390351",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-02T06:33:12Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/uv/pyjwt-2.15.0",
                "remote_freshness": "unknown",
                "revision": "e1db24b75800eef8040e797071c550c9c1bf3842",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-14T16:29:44+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/docs/recall-skill-refresh-20261014",
                "remote_freshness": "unknown",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-13T21:18:00+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/fix/bounded-refresh-health-20261013",
                "remote_freshness": "unknown",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-13T23:22:18+08:00",
                "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
                "ref": "refs/remotes/origin/fix/compact-recall-20261013",
                "remote_freshness": "unknown",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "commit_date": "2026-10-14T16:34:40+08:00",
                "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
                "ref": "refs/remotes/origin/main",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "commit_date": "2026-10-13T21:02:24+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/maintenance/repo-health-20261013",
                "remote_freshness": "unknown",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-06T19:17:55Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/review-20",
                "remote_freshness": "unknown",
                "revision": "88f3ebe08f08a70575208ef6b72bd6289bcc6f4d",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-06T19:18:04Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/review-21",
                "remote_freshness": "unknown",
                "revision": "757a81942bc46b50655584b0553fad7cdc418db1",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-06T19:18:32Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/review-22",
                "remote_freshness": "unknown",
                "revision": "b2f4a2b9afc264ec4b3a884edd5ec7e25fcf15b3",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-06T19:18:40Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/review-23",
                "remote_freshness": "unknown",
                "revision": "18059bd59bb7833af6ab09b4a8218f5f2f08a3ac",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T11:31:18+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/review-9",
                "remote_freshness": "unknown",
                "revision": "35f2eefc639da6e2075d2e7cadd8f84f8d360177",
                "state": "skipped"
              },
              {
                "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "skipped"
              },
              {
                "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/archive-storage/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/public-chatreview-deploy/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer-energy-fix",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              }
            ],
            "document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/workspace/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
            "document_sha256": "bd79e6cad39b35424d248c05be1fa81ea64013a62965c170473d14030f43d844",
            "limitations": [
              "Central snapshot stored in the atlas; not installed or declared canonical in the owner repository.",
              "First-pass bounded feature discovery; no exhaustive function, branch or saved-result audit.",
              "All unselected refs and unreviewed working trees are explicitly retained as coverage gaps."
            ],
            "method": "Read-only local Git-object inspection at pinned commits; manually curated entrypoint slices and statically parsed dependency manifests. No checkout, fetch or owner program execution."
          },
          "source_family_document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/workspace/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
          "source_family_name": "Cross-agent work recall",
          "source_family_purpose": "Find archived prior work and return bounded evidence/navigation for continued inspection."
        }
      ]
    },
    {
      "id": "incremental-source-checkpoints",
      "kind": "module",
      "name": "Incremental archive source checkpoints",
      "purpose": "Select sessions affected by changed source revisions using durable signatures, with full-reconciliation fallback and caller-acknowledged checkpoints.",
      "variants": [
        {
          "access": [
            "Retrieve committed source through the saved helper inventory.",
            "Operational use requires owner instructions, compatible environment and separately authorized artifacts or service/data access."
          ],
          "adoption_notes": [
            "Inspect recorded entrypoint and caller/manifest contracts; compare current owner interfaces before extracting or adopting code.",
            "A branch label and Git ancestry do not establish deployment, current availability or whole-capability equivalence."
          ],
          "atlas_asset_id": "capability-23-open-chat-reviewer-incremental-source-checkpoints-0df414872c12a4e05c56",
          "baseline_equivalence": "unknown",
          "baseline_relation": "diverged",
          "dependencies": [
            {
              "evidence": [
                {
                  "kind": "code",
                  "line": 8,
                  "path": "src/chatreview/source_changes.py",
                  "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da"
                }
              ],
              "name": "chatreview.db.Session",
              "role": "Owner database interface; adapter and transaction semantics must be preserved.",
              "version": null,
              "version_kind": "unknown"
            }
          ],
          "deployment": {
            "receipts": [],
            "status": "unknown"
          },
          "entrypoint_comparison": "identical-entrypoint-blob",
          "entrypoints": [
            "source_changes(connection, key, canonical_dependencies=False); SourceChanges.record(connection)"
          ],
          "evidence": [
            {
              "kind": "code",
              "line": 1,
              "line_end": 70,
              "note": "Source slice read through bundled helper; retrieval receipts retained in this audit round.",
              "path": "src/chatreview/source_changes.py",
              "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
              "sha256": "c3c7de69047f564b5ae8189f94ca8423a63b903c17a9564b48953249cf8507e5"
            },
            {
              "kind": "code",
              "line": 159,
              "line_end": 196,
              "note": "Source slice read through bundled helper; retrieval receipts retained in this audit round.",
              "path": "src/chatreview/episodes.py",
              "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
              "sha256": "062f38ee75cde57477bd44bec3ce51af8546980704c3e881d56c9ca260d4ee9b"
            },
            {
              "kind": "code",
              "line": 636,
              "line_end": 686,
              "note": "Source slice read through bundled helper; retrieval receipts retained in this audit round.",
              "path": "src/chatreview/ingest.py",
              "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
              "sha256": "a03ff9e52bbd45c23e5506424d2aee2ab1774535f4fa980071cbeb4f630bc89e"
            },
            {
              "kind": "code",
              "line": 69,
              "line_end": 82,
              "note": "Source slice read through bundled helper; retrieval receipts retained in this audit round.",
              "path": "src/chatreview/source_changes.py",
              "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
              "sha256": "c3c7de69047f564b5ae8189f94ca8423a63b903c17a9564b48953249cf8507e5"
            }
          ],
          "id": "commit-4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
          "inputs": [
            "Owner database source revision/checkpoint state and a named checkpoint key"
          ],
          "limitations": [
            "Entrypoint is byte-identical to the frozen baseline; branch-only novelty is not established.",
            "The 200-session guard precedes canonical-dependency expansion; it is not a guaranteed upper bound on final output scope.",
            "This is a database-backed refresh mechanism, not a pure filesystem helper. No database was accessed.",
            "Ingestion caller commits session reconciliation before rebuilding registry/rules and recording its checkpoint; do not claim one atomic transaction for the entire refresh.",
            "Bounded source review only; no tests, owner programs, services, database operations, model calls or deployments were run."
          ],
          "maturity": "unknown",
          "maturity_evidence": "Conservative source-audit classification; owner historical-reference rules retained where applicable. Current maintenance and deployment not established.",
          "outputs": [
            "Captured snapshot and changed session IDs, or None requesting full reconciliation"
          ],
          "retrieval_receipts": [
            {
              "line_from": 1,
              "line_to": 70,
              "path": "docs/capability-audits/helper-pilot/2026-10-15/reads/0a2ab0ef2d4ca14d4100836a4b2e4a3637727ed946b29c7bbdc71ff20f9ec1d5.json",
              "sha256": "eb254cfc849afdf0a918bee6d4b62d196d0cfe02dec3119a53d1d7aa7cfdcd77",
              "source_path": "src/chatreview/source_changes.py"
            },
            {
              "line_from": 159,
              "line_to": 196,
              "path": "docs/capability-audits/helper-pilot/2026-10-15/reads/404843890ef5e2cb37eebd24890d1ea0d70f7fb15a54881f55b1b2f6813bf670.json",
              "sha256": "c253686dabb377921d8700f313f663df9deabee185ea975cf73566a0cd60225f",
              "source_path": "src/chatreview/episodes.py"
            },
            {
              "line_from": 636,
              "line_to": 686,
              "path": "docs/capability-audits/helper-pilot/2026-10-15/reads/4d676f851a8fea93179ba853dbdb4c5a9d9a1a3580823b76797d23570188e2cc.json",
              "sha256": "b27bdcd029c2313aca1868c172cfd8e05685bcd726c6bd6d1d38f1a0e54101f4",
              "source_path": "src/chatreview/ingest.py"
            },
            {
              "line_from": 4,
              "line_to": 51,
              "path": "docs/capability-audits/helper-pilot/2026-10-15/reads/5284f29ddf73f099e32a855d64dc85f28a5a938d0e442256bdf945af55e71da5.json",
              "sha256": "3a8884a8abeb701f738991f709d93fee223b1428910b0fcf5cff464f234c5683",
              "source_path": "pyproject.toml"
            },
            {
              "line_from": 1,
              "line_to": 21,
              "path": "docs/capability-audits/helper-pilot/2026-10-15/reads/9afb9390174da8f02a63c7816fefb40b103e2fe3db94c78627566338faf322a4.json",
              "sha256": "ddf77bb4e6729d5d5d827a3740361fe148fbbf5513604cbfebff5988373455ff",
              "source_path": "AGENTS.md"
            },
            {
              "line_from": 69,
              "line_to": 82,
              "path": "docs/capability-audits/helper-pilot/2026-10-15/reads/aa2306fcfe37264a3a8a6faa79bc9a6d8e423630dcbd4c7bbdcbd83e897bc2ab.json",
              "sha256": "1f4d078218f4cfabb604e226991096894a75c962db69f6988fe99ddd8d5d515a",
              "source_path": "src/chatreview/source_changes.py"
            }
          ],
          "runtime": {
            "receipts": [],
            "status": "not-checked"
          },
          "source": {
            "refs": [
              "refs/heads/fix/bounded-refresh-health-20261013",
              "refs/remotes/origin/fix/bounded-refresh-health-20261013"
            ],
            "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
            "working_changes": null,
            "worktree": null
          },
          "source_audit": {
            "baseline": {
              "ref": "refs/remotes/origin/main",
              "revision": "7b0806823e749873803d350618609226e6fcbe04",
              "selection_evidence": "Locally cached default or conventional ref; remote freshness and deployment unknown."
            },
            "checked_at": "2026-10-15",
            "coverage": [
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/archive-storage",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/private-archive-compat",
                "remote_freshness": "not-applicable",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "not-applicable",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/token-cost-projection",
                "remote_freshness": "not-applicable",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/worker-15min",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/docs/recall-skill-refresh-20261014",
                "remote_freshness": "not-applicable",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "skipped"
              },
              {
                "reason": "Selected implementation/caller slices reviewed via helper receipts; entire branch remains unreviewed.",
                "ref": "refs/heads/fix/bounded-refresh-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "partial"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/heads/fix/compact-recall-20261013",
                "remote_freshness": "not-applicable",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/fix/idle-database-churn-20261007",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/heads/main",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/maintenance/repo-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/remotes/origin/HEAD",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/archive-storage",
                "remote_freshness": "unknown",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/private-archive-compat",
                "remote_freshness": "unknown",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "unknown",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/token-cost-projection",
                "remote_freshness": "unknown",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/worker-15min",
                "remote_freshness": "unknown",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "8c1dadc2aeeef60022a346ed77aae12e450040fb",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "141efe84ae5068dec98d28a7427458e8c4468228",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-13a777b093",
                "remote_freshness": "unknown",
                "revision": "11a5e5c62412875a4c20b1bb3b02ca50651ff407",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-3457e10658",
                "remote_freshness": "unknown",
                "revision": "796791c5604f660dd02281709f958746974330d1",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-03db81fe05",
                "remote_freshness": "unknown",
                "revision": "661b22c4b41ddefd10386d5ada86a6ece7c6d4a2",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-2514a98571",
                "remote_freshness": "unknown",
                "revision": "cf7a89c7c7231e5f57e03c2437fcf7dd14501828",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "2024029bd0939a2f7bf1b2edf7d1a181b2a1314f",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/lucide-react-1.37.0",
                "remote_freshness": "unknown",
                "revision": "e905acafa5bcaedcdf9dbe539879b37ea2023edb",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "e1c3295c90021cd73c513e4ffe076a6986bbf253",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vite-8.2.2",
                "remote_freshness": "unknown",
                "revision": "2bade23ace71fb47b7273185466aedc317b82966",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vitest-4.1.11",
                "remote_freshness": "unknown",
                "revision": "f743dafa78068d7006d95e39d690d3edbfcad23e",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/pip/mcp-gte-1.12-and-lt-3",
                "remote_freshness": "unknown",
                "revision": "934cb7738cf8bf49fc6e1317dcabdafdb1452418",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/pip/uv-build-gte-0.8.0-and-lt-0.13",
                "remote_freshness": "unknown",
                "revision": "760b245daa7e818200b3c508849323fa86390351",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/uv/pyjwt-2.15.0",
                "remote_freshness": "unknown",
                "revision": "e1db24b75800eef8040e797071c550c9c1bf3842",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/docs/recall-skill-refresh-20261014",
                "remote_freshness": "unknown",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "skipped"
              },
              {
                "reason": "Selected implementation/caller slices reviewed via helper receipts; entire branch remains unreviewed.",
                "ref": "refs/remotes/origin/fix/bounded-refresh-health-20261013",
                "remote_freshness": "unknown",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "partial"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/remotes/origin/fix/compact-recall-20261013",
                "remote_freshness": "unknown",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/remotes/origin/main",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/maintenance/repo-health-20261013",
                "remote_freshness": "unknown",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-20",
                "remote_freshness": "unknown",
                "revision": "88f3ebe08f08a70575208ef6b72bd6289bcc6f4d",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-21",
                "remote_freshness": "unknown",
                "revision": "757a81942bc46b50655584b0553fad7cdc418db1",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-22",
                "remote_freshness": "unknown",
                "revision": "b2f4a2b9afc264ec4b3a884edd5ec7e25fcf15b3",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-23",
                "remote_freshness": "unknown",
                "revision": "18059bd59bb7833af6ab09b4a8218f5f2f08a3ac",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-9",
                "remote_freshness": "unknown",
                "revision": "35f2eefc639da6e2075d2e7cadd8f84f8d360177",
                "state": "skipped"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/tags/recall-skill-20261014",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/tags/v0.1.0-alpha.1",
                "remote_freshness": "not-applicable",
                "revision": "b027ccae1c42a87bbf5b81e1a4280de7e81ba77f",
                "state": "skipped"
              },
              {
                "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "skipped"
              },
              {
                "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/archive-storage/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/public-chatreview-deploy/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer-energy-fix",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              }
            ],
            "document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/helper-pilot/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
            "document_sha256": "c10a7a3ef461bedc53e8f7700f66594c9ac9f0db263e3819c8b4fdfaf2e2c93e",
            "limitations": [
              "Central atlas snapshot, not installed in owner repositories.",
              "Six selected previously uninspected branch tips across five repositories; not an exhaustive audit.",
              "Source read receipts prove retrieval only; capability evidence names the reviewed code slices."
            ],
            "method": "Bundled helper inventory plus source excerpts at pinned commits, followed by agent interpretation and exact entrypoint blob comparisons."
          },
          "source_family_document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/helper-pilot/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
          "source_family_name": "Incremental archive source checkpoints",
          "source_family_purpose": "Select sessions affected by changed source revisions using durable signatures, with full-reconciliation fallback and caller-acknowledged checkpoints."
        }
      ]
    },
    {
      "id": "recall-mcp",
      "kind": "interface",
      "name": "Bounded archive MCP interface",
      "purpose": "Expose bounded archive discovery/read tools over the recall implementation.",
      "variants": [
        {
          "access": [
            "Read source at the recorded revision with git show <revision>:<path>.",
            "Runtime use requires the owner repository instructions, compatible environment and separately authorized data/service access; no access was established by this audit."
          ],
          "adoption_notes": [
            "Review this immutable entrypoint, relevant callers and dependency manifests before extracting an interface or comparing competing implementations.",
            "Do not infer a runnable combined pipeline from capabilities on different branches. Confirm contracts and current owner authority independently."
          ],
          "atlas_asset_id": "capability-23-open-chat-reviewer-recall-mcp-57f938e78e29bf280093",
          "baseline_equivalence": "unknown",
          "baseline_relation": "diverged",
          "dependencies": [
            {
              "evidence": [
                {
                  "kind": "code",
                  "path": "src/chatreview/archive_mcp.py",
                  "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b"
                }
              ],
              "name": "mcp",
              "role": "Direct import in inspected entrypoint; package mapping/version unresolved.",
              "version": null,
              "version_kind": "unknown"
            }
          ],
          "deployment": {
            "receipts": [],
            "status": "unknown"
          },
          "entrypoint_comparison": "identical-entrypoint-blob",
          "entrypoints": [
            "src/chatreview/archive_mcp.py (inspect implementation and owner command/contract before invocation)"
          ],
          "evidence": [
            {
              "kind": "code",
              "line": 1,
              "line_end": 10,
              "note": "Bounded source inspection; see source-reads.jsonl for receipt.",
              "path": "src/chatreview/archive_mcp.py",
              "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
              "sha256": "c2a79b5fd4987a940fccba6c578e992cadf4eb2e8116e1388d0c764859bb6b6e"
            },
            {
              "kind": "code",
              "line": 15,
              "line_end": 49,
              "note": "Bounded source inspection; see source-reads.jsonl for receipt.",
              "path": "src/chatreview/archive_mcp.py",
              "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
              "sha256": "c2a79b5fd4987a940fccba6c578e992cadf4eb2e8116e1388d0c764859bb6b6e"
            }
          ],
          "id": "commit-046d85ac80f6246a04e88390f49cc81c6c89b43b",
          "inputs": [
            "Read-only archive tool request"
          ],
          "limitations": [
            "Only the cited source slices were inspected; callers, complete pipelines, saved experiment outcomes and operational readiness were not exhaustively reviewed.",
            "Dirty worktree contents were not inspected. Cached remote freshness, current access, deployment and runtime success are unknown."
          ],
          "maturity": "experimental",
          "maturity_evidence": "Conservatively treated as experimental for selected nonbaseline research/work-in-progress snapshots; this is not a deployment assessment.",
          "outputs": [
            "Bounded original evidence and continuation metadata"
          ],
          "runtime": {
            "receipts": [],
            "status": "not-checked"
          },
          "source": {
            "refs": [
              "refs/heads/fix/compact-recall-20261013",
              "refs/remotes/origin/fix/compact-recall-20261013"
            ],
            "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
            "working_changes": null,
            "worktree": null
          },
          "source_audit": {
            "baseline": {
              "ref": "refs/remotes/origin/main",
              "revision": "7b0806823e749873803d350618609226e6fcbe04",
              "selection_evidence": "Locally cached origin default if available, otherwise conventional main/master or current HEAD; no fetch, not deployment evidence."
            },
            "checked_at": "2026-10-15",
            "coverage": [
              {
                "commit_date": "2026-09-29T11:39:41+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/codex/archive-storage",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-28T23:02:17+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/codex/private-archive-compat",
                "remote_freshness": "not-applicable",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T12:02:59+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "not-applicable",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T12:51:46+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/codex/token-cost-projection",
                "remote_freshness": "not-applicable",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-28T23:14:16+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/codex/worker-15min",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-14T16:29:44+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/docs/recall-skill-refresh-20261014",
                "remote_freshness": "not-applicable",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-13T21:18:00+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/fix/bounded-refresh-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-13T23:22:18+08:00",
                "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
                "ref": "refs/heads/fix/compact-recall-20261013",
                "remote_freshness": "not-applicable",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "commit_date": "2026-10-07T22:29:24+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/fix/idle-database-churn-20261007",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-14T16:34:40+08:00",
                "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
                "ref": "refs/heads/main",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "commit_date": "2026-10-13T21:02:24+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/heads/maintenance/repo-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-14T16:34:40+08:00",
                "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
                "ref": "refs/remotes/origin/HEAD",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "commit_date": "2026-09-29T11:39:41+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/codex/archive-storage",
                "remote_freshness": "unknown",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-28T23:02:17+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/codex/private-archive-compat",
                "remote_freshness": "unknown",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T12:02:59+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "unknown",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T12:51:46+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/codex/token-cost-projection",
                "remote_freshness": "unknown",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-28T23:14:16+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/codex/worker-15min",
                "remote_freshness": "unknown",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T04:07:39Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/bun/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "8c1dadc2aeeef60022a346ed77aae12e450040fb",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T04:07:35Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/bun/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "141efe84ae5068dec98d28a7427458e8c4468228",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-27T19:18:30Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-13a777b093",
                "remote_freshness": "unknown",
                "revision": "11a5e5c62412875a4c20b1bb3b02ca50651ff407",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-11T19:19:48Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-3457e10658",
                "remote_freshness": "unknown",
                "revision": "796791c5604f660dd02281709f958746974330d1",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-04T19:33:06Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-03db81fe05",
                "remote_freshness": "unknown",
                "revision": "661b22c4b41ddefd10386d5ada86a6ece7c6d4a2",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-03T04:00:09Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-2514a98571",
                "remote_freshness": "unknown",
                "revision": "cf7a89c7c7231e5f57e03c2437fcf7dd14501828",
                "state": "skipped"
              },
              {
                "commit_date": "2026-08-30T01:04:00Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "2024029bd0939a2f7bf1b2edf7d1a181b2a1314f",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-03T04:01:27Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/lucide-react-1.37.0",
                "remote_freshness": "unknown",
                "revision": "e905acafa5bcaedcdf9dbe539879b37ea2023edb",
                "state": "skipped"
              },
              {
                "commit_date": "2026-08-30T01:03:54Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "e1c3295c90021cd73c513e4ffe076a6986bbf253",
                "state": "skipped"
              },
              {
                "commit_date": "2026-08-30T01:03:52Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vite-8.2.2",
                "remote_freshness": "unknown",
                "revision": "2bade23ace71fb47b7273185466aedc317b82966",
                "state": "skipped"
              },
              {
                "commit_date": "2026-08-30T01:04:03Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vitest-4.1.11",
                "remote_freshness": "unknown",
                "revision": "f743dafa78068d7006d95e39d690d3edbfcad23e",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-13T19:04:49Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/pip/mcp-gte-1.12-and-lt-3",
                "remote_freshness": "unknown",
                "revision": "934cb7738cf8bf49fc6e1317dcabdafdb1452418",
                "state": "skipped"
              },
              {
                "commit_date": "2026-08-30T01:03:40Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/pip/uv-build-gte-0.8.0-and-lt-0.13",
                "remote_freshness": "unknown",
                "revision": "760b245daa7e818200b3c508849323fa86390351",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-02T06:33:12Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/dependabot/uv/pyjwt-2.15.0",
                "remote_freshness": "unknown",
                "revision": "e1db24b75800eef8040e797071c550c9c1bf3842",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-14T16:29:44+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/docs/recall-skill-refresh-20261014",
                "remote_freshness": "unknown",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-13T21:18:00+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/fix/bounded-refresh-health-20261013",
                "remote_freshness": "unknown",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "skipped"
              },
              {
                "commit_date": "2026-10-13T23:22:18+08:00",
                "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
                "ref": "refs/remotes/origin/fix/compact-recall-20261013",
                "remote_freshness": "unknown",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "commit_date": "2026-10-14T16:34:40+08:00",
                "reason": "Selected entrypoint slices inspected at this exact commit; broader branch source unreviewed.",
                "ref": "refs/remotes/origin/main",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "commit_date": "2026-10-13T21:02:24+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/maintenance/repo-health-20261013",
                "remote_freshness": "unknown",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-06T19:17:55Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/review-20",
                "remote_freshness": "unknown",
                "revision": "88f3ebe08f08a70575208ef6b72bd6289bcc6f4d",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-06T19:18:04Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/review-21",
                "remote_freshness": "unknown",
                "revision": "757a81942bc46b50655584b0553fad7cdc418db1",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-06T19:18:32Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/review-22",
                "remote_freshness": "unknown",
                "revision": "b2f4a2b9afc264ec4b3a884edd5ec7e25fcf15b3",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-06T19:18:40Z",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/review-23",
                "remote_freshness": "unknown",
                "revision": "18059bd59bb7833af6ab09b4a8218f5f2f08a3ac",
                "state": "skipped"
              },
              {
                "commit_date": "2026-09-07T11:31:18+08:00",
                "reason": "Inventoried only; not selected for source-level inspection in this bounded first pass.",
                "ref": "refs/remotes/origin/review-9",
                "remote_freshness": "unknown",
                "revision": "35f2eefc639da6e2075d2e7cadd8f84f8d360177",
                "state": "skipped"
              },
              {
                "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "skipped"
              },
              {
                "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/archive-storage/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/public-chatreview-deploy/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Worktree location/HEAD inventoried; working files and untracked experiments not inspected. Committed slices, if reviewed, are recorded separately by revision.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer-energy-fix",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              }
            ],
            "document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/workspace/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
            "document_sha256": "bd79e6cad39b35424d248c05be1fa81ea64013a62965c170473d14030f43d844",
            "limitations": [
              "Central snapshot stored in the atlas; not installed or declared canonical in the owner repository.",
              "First-pass bounded feature discovery; no exhaustive function, branch or saved-result audit.",
              "All unselected refs and unreviewed working trees are explicitly retained as coverage gaps."
            ],
            "method": "Read-only local Git-object inspection at pinned commits; manually curated entrypoint slices and statically parsed dependency manifests. No checkout, fetch or owner program execution."
          },
          "source_family_document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/workspace/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
          "source_family_name": "Bounded archive MCP interface",
          "source_family_purpose": "Expose bounded archive discovery/read tools over the recall implementation."
        }
      ]
    },
    {
      "id": "recall-skill-installer",
      "kind": "CLI",
      "name": "Portable recall-skill installer",
      "purpose": "Copy portable recall guidance to compatibility/current agent skill directories, back up existing content and verify copied file hashes.",
      "variants": [
        {
          "access": [
            "Retrieve committed source through the saved helper inventory.",
            "Operational use requires owner instructions, compatible environment and separately authorized artifacts or service/data access."
          ],
          "adoption_notes": [
            "Inspect recorded entrypoint and caller/manifest contracts; compare current owner interfaces before extracting or adopting code.",
            "A branch label and Git ancestry do not establish deployment, current availability or whole-capability equivalence."
          ],
          "atlas_asset_id": "capability-23-open-chat-reviewer-recall-skill-installer-b024e0ee88108cb5a0e0",
          "baseline_equivalence": "unknown",
          "baseline_relation": "diverged",
          "dependencies": [],
          "deployment": {
            "receipts": [],
            "status": "unknown"
          },
          "entrypoint_comparison": "identical-entrypoint-blob",
          "entrypoints": [
            "scripts/install-recall-skill.py --source DIRECTORY --home DIRECTORY"
          ],
          "evidence": [
            {
              "kind": "code",
              "line": 1,
              "line_end": 48,
              "note": "Source slice read through bundled helper; retrieval receipts retained in this audit round.",
              "path": "scripts/install-recall-skill.py",
              "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
              "sha256": "f70e06de4fddc33d824a882ab0075c218e3b5bf165ca7e504654bae733597cb2"
            },
            {
              "kind": "code",
              "line": 1,
              "line_end": 32,
              "note": "Source slice read through bundled helper; retrieval receipts retained in this audit round.",
              "path": "scripts/install-recall-skill.py",
              "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
              "sha256": "f70e06de4fddc33d824a882ab0075c218e3b5bf165ca7e504654bae733597cb2"
            }
          ],
          "id": "commit-198143467bf854501420bf89a39eb96fa2fcc219",
          "inputs": [
            "Complete chatreview-recall skill tree and destination home"
          ],
          "limitations": [
            "Writes user skill directories when invoked; the audit only read its source and did not install anything.",
            "Does not alter MCP configuration. Copies over existing trees without removing stale target-only files; whole-tree equality/rollback is not established.",
            "The entrypoint is byte-identical to the frozen baseline: newly documented reuse, not a branch-only feature.",
            "Bounded source review only; no tests, owner programs, services, database operations, model calls or deployments were run."
          ],
          "maturity": "unknown",
          "maturity_evidence": "Conservative source-audit classification; owner historical-reference rules retained where applicable. Current maintenance and deployment not established.",
          "outputs": [
            "Installed skill copies, timestamped backup and JSON installation receipt"
          ],
          "retrieval_receipts": [
            {
              "line_from": 1,
              "line_to": 21,
              "path": "docs/capability-audits/branch-continuation/2026-10-15/reads/0577ee620161fde5465f154e7746286d1e4158f4f869855c43b69ce2c686a7bc.json",
              "sha256": "b22c9c6e1af60b387335fd1596c21bda2a0558227c93b6856bdca05ba0b14a4f",
              "source_path": "AGENTS.md"
            },
            {
              "line_from": 1,
              "line_to": 48,
              "path": "docs/capability-audits/branch-continuation/2026-10-15/reads/7cac78b13dd93906906350e7b62b1b6ac5abf45499b418086e50a17b99ba984c.json",
              "sha256": "4e93b02c5833677056e9d6ded93eaac75d6981338fc846614e4f2bb9cfe81495",
              "source_path": "scripts/install-recall-skill.py"
            },
            {
              "line_from": 1,
              "line_to": 32,
              "path": "docs/capability-audits/branch-continuation/2026-10-15/reads/e5392f9b03d5ef1241a5aa9959b4669eb6ae67000a56dd618a85c3f400c9849c.json",
              "sha256": "411732e5400ff89ac93e40d15354e5d92e5236f228e804f1dca4440d8d63e57f",
              "source_path": "scripts/install-recall-skill.py"
            }
          ],
          "runtime": {
            "receipts": [],
            "status": "not-checked"
          },
          "source": {
            "refs": [
              "refs/heads/docs/recall-skill-refresh-20261014",
              "refs/remotes/origin/docs/recall-skill-refresh-20261014"
            ],
            "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
            "working_changes": null,
            "worktree": null
          },
          "source_audit": {
            "baseline": {
              "ref": "refs/remotes/origin/main",
              "revision": "7b0806823e749873803d350618609226e6fcbe04",
              "selection_evidence": "Locally cached default or conventional ref; remote freshness and deployment unknown."
            },
            "checked_at": "2026-10-15",
            "coverage": [
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/archive-storage",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/private-archive-compat",
                "remote_freshness": "not-applicable",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "not-applicable",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/token-cost-projection",
                "remote_freshness": "not-applicable",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/worker-15min",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Selected implementation/caller slices reviewed via helper receipts; entire branch remains unreviewed.",
                "ref": "refs/heads/docs/recall-skill-refresh-20261014",
                "remote_freshness": "not-applicable",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "partial"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/heads/fix/bounded-refresh-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "partial"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/heads/fix/compact-recall-20261013",
                "remote_freshness": "not-applicable",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/fix/idle-database-churn-20261007",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/heads/main",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/maintenance/repo-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/remotes/origin/HEAD",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/archive-storage",
                "remote_freshness": "unknown",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/private-archive-compat",
                "remote_freshness": "unknown",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "unknown",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/token-cost-projection",
                "remote_freshness": "unknown",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/worker-15min",
                "remote_freshness": "unknown",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "8c1dadc2aeeef60022a346ed77aae12e450040fb",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "141efe84ae5068dec98d28a7427458e8c4468228",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-13a777b093",
                "remote_freshness": "unknown",
                "revision": "11a5e5c62412875a4c20b1bb3b02ca50651ff407",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-3457e10658",
                "remote_freshness": "unknown",
                "revision": "796791c5604f660dd02281709f958746974330d1",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-03db81fe05",
                "remote_freshness": "unknown",
                "revision": "661b22c4b41ddefd10386d5ada86a6ece7c6d4a2",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-2514a98571",
                "remote_freshness": "unknown",
                "revision": "cf7a89c7c7231e5f57e03c2437fcf7dd14501828",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "2024029bd0939a2f7bf1b2edf7d1a181b2a1314f",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/lucide-react-1.37.0",
                "remote_freshness": "unknown",
                "revision": "e905acafa5bcaedcdf9dbe539879b37ea2023edb",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "e1c3295c90021cd73c513e4ffe076a6986bbf253",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vite-8.2.2",
                "remote_freshness": "unknown",
                "revision": "2bade23ace71fb47b7273185466aedc317b82966",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vitest-4.1.11",
                "remote_freshness": "unknown",
                "revision": "f743dafa78068d7006d95e39d690d3edbfcad23e",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/pip/mcp-gte-1.12-and-lt-3",
                "remote_freshness": "unknown",
                "revision": "934cb7738cf8bf49fc6e1317dcabdafdb1452418",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/pip/uv-build-gte-0.8.0-and-lt-0.13",
                "remote_freshness": "unknown",
                "revision": "760b245daa7e818200b3c508849323fa86390351",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/uv/pyjwt-2.15.0",
                "remote_freshness": "unknown",
                "revision": "e1db24b75800eef8040e797071c550c9c1bf3842",
                "state": "skipped"
              },
              {
                "reason": "Selected implementation/caller slices reviewed via helper receipts; entire branch remains unreviewed.",
                "ref": "refs/remotes/origin/docs/recall-skill-refresh-20261014",
                "remote_freshness": "unknown",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "partial"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/remotes/origin/fix/bounded-refresh-health-20261013",
                "remote_freshness": "unknown",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "partial"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/remotes/origin/fix/compact-recall-20261013",
                "remote_freshness": "unknown",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/remotes/origin/main",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/maintenance/repo-health-20261013",
                "remote_freshness": "unknown",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-20",
                "remote_freshness": "unknown",
                "revision": "88f3ebe08f08a70575208ef6b72bd6289bcc6f4d",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-21",
                "remote_freshness": "unknown",
                "revision": "757a81942bc46b50655584b0553fad7cdc418db1",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-22",
                "remote_freshness": "unknown",
                "revision": "b2f4a2b9afc264ec4b3a884edd5ec7e25fcf15b3",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-23",
                "remote_freshness": "unknown",
                "revision": "18059bd59bb7833af6ab09b4a8218f5f2f08a3ac",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-9",
                "remote_freshness": "unknown",
                "revision": "35f2eefc639da6e2075d2e7cadd8f84f8d360177",
                "state": "skipped"
              },
              {
                "reason": "Exact revision has a prior capability source record; wider branch remains unreviewed.",
                "ref": "refs/tags/recall-skill-20261014",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/tags/v0.1.0-alpha.1",
                "remote_freshness": "not-applicable",
                "revision": "b027ccae1c42a87bbf5b81e1a4280de7e81ba77f",
                "state": "skipped"
              },
              {
                "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "skipped"
              },
              {
                "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/archive-storage/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/public-chatreview-deploy/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Location and HEAD inventoried; dirty/untracked working-file contents excluded.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer-energy-fix",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              }
            ],
            "document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/branch-continuation/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
            "document_sha256": "fa661133be7c7d34cd6594fcc89f495c7b85d4c82c130938db33549f1d96201b",
            "limitations": [
              "Central atlas snapshot, not installed in owner repositories.",
              "Twenty selected previously uninspected tips across fourteen checkout groups; not an exhaustive audit.",
              "Source read receipts prove retrieval only; capability evidence names the reviewed code slices."
            ],
            "method": "Bundled helper inventory plus source excerpts at pinned commits, followed by agent interpretation and exact entrypoint blob comparisons."
          },
          "source_family_document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/branch-continuation/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
          "source_family_name": "Portable recall-skill installer",
          "source_family_purpose": "Copy portable recall guidance to compatibility/current agent skill directories, back up existing content and verify copied file hashes."
        }
      ]
    },
    {
      "id": "shared-timesheet-evidence",
      "kind": "database module",
      "name": "Shared content-addressed timesheet evidence",
      "purpose": "Deduplicate canonical event/episode membership sets by deterministic fingerprints and keep interval occurrences as separate references.",
      "variants": [
        {
          "access": [
            "Retrieve committed source at the full revision using the frozen helper inventory.",
            "Operational use requires owner instructions, compatible environment and separately authorized artifact, database, service or provider access."
          ],
          "adoption_notes": [
            "Review entrypoint, caller, dependency and recorded limitations before extracting/adapting code. Preserve canonical owner and evidence boundaries.",
            "Branch labels and ancestry do not establish deployment or whole-capability equivalence."
          ],
          "atlas_asset_id": "capability-23-open-chat-reviewer-shared-timesheet-evidence-11b2535a8309b1faff44",
          "baseline_equivalence": "unknown",
          "baseline_relation": "diverged",
          "dependencies": [
            {
              "evidence": [
                {
                  "kind": "code",
                  "path": "src/chatreview/shared_evidence.py",
                  "revision": "3c0116952296b57951210d0a843ce13f44ce576c"
                }
              ],
              "name": "Owner chatreview.db.Session",
              "role": "Significant direct dependency, required runtime or owner interface; source slices and manifest declarations retained where inspected.",
              "version": null,
              "version_kind": "unknown"
            },
            {
              "evidence": [
                {
                  "kind": "documentation",
                  "line": 23,
                  "path": "pyproject.toml",
                  "revision": "3c0116952296b57951210d0a843ce13f44ce576c"
                }
              ],
              "name": "psycopg",
              "role": "Significant direct dependency, required runtime or owner interface; source slices and manifest declarations retained where inspected.",
              "version": ">=3.2",
              "version_kind": "constraint"
            }
          ],
          "deployment": {
            "receipts": [],
            "status": "unknown"
          },
          "entrypoint_comparison": "identical-entrypoint-blob",
          "entrypoints": [
            "canonical_members(rows); evidence_fingerprint(members); persist_evidence(connection, rows)"
          ],
          "evidence": [
            {
              "kind": "code",
              "line": 1,
              "line_end": 89,
              "note": "Agent-reviewed committed source slice retrieved with bundled helper; receipt retained.",
              "path": "src/chatreview/shared_evidence.py",
              "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
              "sha256": "19f5bb1e1ac15690d1a741461ef636dda13eec14b053aec72e732e802e03829b"
            },
            {
              "kind": "code",
              "line": 1104,
              "line_end": 1135,
              "note": "Agent-reviewed committed source slice retrieved with bundled helper; receipt retained.",
              "path": "src/chatreview/timesheets.py",
              "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
              "sha256": "c12b26ed4648e6ddf56255989f63c97e7bc15a855433d017d55b56b044924455"
            }
          ],
          "id": "commit-3c0116952296b57951210d0a843ce13f44ce576c",
          "inputs": [
            "Owner event/episode identity pairs and database session"
          ],
          "limitations": [
            "Fingerprint binds membership identities, not hashes of raw source messages. Reuse must preserve event/episode identity and owner migration/transaction contracts.",
            "persist_evidence writes sets/members; the timesheet caller links occurrences and commits. No database size reduction or migration completion was measured.",
            "Selected entry file is byte-identical to the frozen baseline. This is newly documented reuse, not a claim of branch-only novelty.",
            "Bounded source inspection only. No tests, models, owner programs, services, data reads/writes or deployments were run."
          ],
          "maturity": "unknown",
          "maturity_evidence": "Conservative source-only classification. Historical prototype status retained for review UI; owner maintenance and deployment not established.",
          "outputs": [
            "Stable membership fingerprint and evidence-set ID; interval-to-evidence references"
          ],
          "retrieval_receipts": [
            {
              "line_from": 1,
              "line_to": 17,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/206afe841e14a7669809c69ea343eafc03a86ee0f821f886bf9f6dd3ca834395.json",
              "sha256": "236d8de4eae8cd5edbfca61d6839022836faf8b30db77ddad23749ee04de0a7e",
              "source_path": "AGENTS.md"
            },
            {
              "line_from": 1,
              "line_to": 26,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/3d4fd06fe530e0e36639c0f9a25ded178be1630e5781ee5eeaced06a8430bb8f.json",
              "sha256": "cfadea7820bfcb4c7002fa6929ef1cffbc38b5bada82998508b8bcd4dfd4276c",
              "source_path": "README.md"
            },
            {
              "line_from": 1,
              "line_to": 89,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/4fbe761d9f59c1985a82c918ba63f63e9ad43c8f0c7d9372a03f08a4a08c9239.json",
              "sha256": "54f23e4d55cde70f876a58f09bdad042c4d6df7a0012ba7419279b93ae7f1f69",
              "source_path": "src/chatreview/shared_evidence.py"
            },
            {
              "line_from": 22,
              "line_to": 24,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/8b42f3ae61001544ed864f1160eee3b1ea9fecb403436ad7f6eac38e9ed15fc4.json",
              "sha256": "758c511a8a6196e13a1369355abb649063cb1edd49ff13ac8354d972ca05aae1",
              "source_path": "pyproject.toml"
            },
            {
              "line_from": 1104,
              "line_to": 1135,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/c61b9f7292b79dd7b4e5a01654cb6b730ce5ce5392a9914e5673a3b7f52a7881.json",
              "sha256": "a22c160b921452a19b0d4b931180cb86a0416367d3ec46055c8a00b63641725b",
              "source_path": "src/chatreview/timesheets.py"
            },
            {
              "line_from": 23,
              "line_to": 25,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/f42cb0e7a4632a4de94c8c861fd827bf3a9301ecafa34fa5ee6a30085e846a3f.json",
              "sha256": "10385f9aa0a3077a43ad731aed70d69999eb74c3a2f680e30e363894e3a815e7",
              "source_path": "pyproject.toml"
            }
          ],
          "reuse_assessment": {
            "schema": "canetoad-reuse/v1",
            "category": "adapter-required",
            "work_needed": [
              "documentation",
              "example",
              "adapter",
              "access",
              "design",
              "verification"
            ],
            "effort": "medium",
            "target_use": "Deduplicated evidence membership sets in a compatible review or timesheet database, with interval occurrences retained as separate links.",
            "next_step": "Specify an owner-neutral evidence-set and occurrence contract, then implement an adapter for the target session, tables, transaction boundary and event/episode identity semantics.",
            "success_check": "Equivalent membership rows produce one stable versioned fingerprint and set ID, conflicting episode membership is rejected, interval occurrences remain distinct, and rollback/commit behavior is documented for the target schema.",
            "basis": "The pinned module exposes a small deterministic canonicalization/fingerprint surface, but persist_evidence is coupled to the owner's Session and database tables. The timesheet caller owns occurrence linkage and commit behavior, while psycopg is declared as a dependency. Reuse therefore needs a schema and transaction adapter even though the hash logic is portable.",
            "assessed_at": "2026-10-15",
            "confidence": "high",
            "evidence": [
              {
                "path": "src/chatreview/shared_evidence.py",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "kind": "code",
                "note": "Canonical membership, deterministic v1 fingerprinting, idempotent insertion and integrity checks were inspected."
              },
              {
                "path": "src/chatreview/timesheets.py",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "kind": "code",
                "note": "The caller's interval occurrence linkage boundary was inspected."
              },
              {
                "path": "pyproject.toml",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "kind": "documentation",
                "note": "The psycopg dependency constraint was inspected; installed resolution was not checked."
              }
            ]
          },
          "runtime": {
            "receipts": [],
            "status": "not-checked"
          },
          "source": {
            "refs": [
              "refs/heads/codex/archive-storage",
              "refs/remotes/origin/codex/archive-storage"
            ],
            "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
            "working_changes": null,
            "worktree": null
          },
          "source_audit": {
            "baseline": {
              "ref": "refs/remotes/origin/main",
              "revision": "7b0806823e749873803d350618609226e6fcbe04",
              "selection_evidence": "Locally cached default or conventional ref; remote freshness and deployment unknown."
            },
            "checked_at": "2026-10-15",
            "coverage": [
              {
                "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
                "ref": "refs/heads/codex/archive-storage",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/private-archive-compat",
                "remote_freshness": "not-applicable",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "not-applicable",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
                "ref": "refs/heads/codex/token-cost-projection",
                "remote_freshness": "not-applicable",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/worker-15min",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/heads/docs/recall-skill-refresh-20261014",
                "remote_freshness": "not-applicable",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "partial"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/heads/fix/bounded-refresh-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "partial"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/heads/fix/compact-recall-20261013",
                "remote_freshness": "not-applicable",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/fix/idle-database-churn-20261007",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/heads/main",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/maintenance/repo-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/remotes/origin/HEAD",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
                "ref": "refs/remotes/origin/codex/archive-storage",
                "remote_freshness": "unknown",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/private-archive-compat",
                "remote_freshness": "unknown",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "unknown",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
                "ref": "refs/remotes/origin/codex/token-cost-projection",
                "remote_freshness": "unknown",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/worker-15min",
                "remote_freshness": "unknown",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "8c1dadc2aeeef60022a346ed77aae12e450040fb",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "141efe84ae5068dec98d28a7427458e8c4468228",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-13a777b093",
                "remote_freshness": "unknown",
                "revision": "11a5e5c62412875a4c20b1bb3b02ca50651ff407",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-3457e10658",
                "remote_freshness": "unknown",
                "revision": "796791c5604f660dd02281709f958746974330d1",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-03db81fe05",
                "remote_freshness": "unknown",
                "revision": "661b22c4b41ddefd10386d5ada86a6ece7c6d4a2",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-2514a98571",
                "remote_freshness": "unknown",
                "revision": "cf7a89c7c7231e5f57e03c2437fcf7dd14501828",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "2024029bd0939a2f7bf1b2edf7d1a181b2a1314f",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/lucide-react-1.37.0",
                "remote_freshness": "unknown",
                "revision": "e905acafa5bcaedcdf9dbe539879b37ea2023edb",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "e1c3295c90021cd73c513e4ffe076a6986bbf253",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vite-8.2.2",
                "remote_freshness": "unknown",
                "revision": "2bade23ace71fb47b7273185466aedc317b82966",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vitest-4.1.11",
                "remote_freshness": "unknown",
                "revision": "f743dafa78068d7006d95e39d690d3edbfcad23e",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/pip/mcp-gte-1.12-and-lt-3",
                "remote_freshness": "unknown",
                "revision": "934cb7738cf8bf49fc6e1317dcabdafdb1452418",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/pip/uv-build-gte-0.8.0-and-lt-0.13",
                "remote_freshness": "unknown",
                "revision": "760b245daa7e818200b3c508849323fa86390351",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/uv/pyjwt-2.15.0",
                "remote_freshness": "unknown",
                "revision": "e1db24b75800eef8040e797071c550c9c1bf3842",
                "state": "skipped"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/remotes/origin/docs/recall-skill-refresh-20261014",
                "remote_freshness": "unknown",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "partial"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/remotes/origin/fix/bounded-refresh-health-20261013",
                "remote_freshness": "unknown",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "partial"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/remotes/origin/fix/compact-recall-20261013",
                "remote_freshness": "unknown",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/remotes/origin/main",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/maintenance/repo-health-20261013",
                "remote_freshness": "unknown",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-20",
                "remote_freshness": "unknown",
                "revision": "88f3ebe08f08a70575208ef6b72bd6289bcc6f4d",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-21",
                "remote_freshness": "unknown",
                "revision": "757a81942bc46b50655584b0553fad7cdc418db1",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-22",
                "remote_freshness": "unknown",
                "revision": "b2f4a2b9afc264ec4b3a884edd5ec7e25fcf15b3",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-23",
                "remote_freshness": "unknown",
                "revision": "18059bd59bb7833af6ab09b4a8218f5f2f08a3ac",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-9",
                "remote_freshness": "unknown",
                "revision": "35f2eefc639da6e2075d2e7cadd8f84f8d360177",
                "state": "skipped"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/tags/recall-skill-20261014",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/tags/v0.1.0-alpha.1",
                "remote_freshness": "not-applicable",
                "revision": "b027ccae1c42a87bbf5b81e1a4280de7e81ba77f",
                "state": "skipped"
              },
              {
                "reason": "Location/HEAD inventoried; working files excluded.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "skipped"
              },
              {
                "reason": "Location/HEAD inventoried; working files excluded.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/archive-storage/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "reason": "Location/HEAD inventoried; working files excluded.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/public-chatreview-deploy/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Location/HEAD inventoried; working files excluded.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer-energy-fix",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              }
            ],
            "document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/reuse-priority/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
            "document_sha256": "6314ede0f45b3dd9541229214557429a7d79ec579e0a29e4324135bafa6d8641",
            "limitations": [
              "Central snapshot only; not installed in owner repository.",
              "Sixteen selected previously uninspected tips across thirteen repositories; not an exhaustive audit.",
              "Inventory capture time is retained from the previous round; no fetch or current-ref assertion.",
              "Retrieval receipts prove retrieval, not complete review."
            ],
            "method": "Bundled helper source reads against the unchanged branch-continuation frozen inventory, followed by interpretation of selected implementation/caller/dependency slices and exact entry-file comparisons."
          },
          "source_family_document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/reuse-priority/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
          "source_family_name": "Shared content-addressed timesheet evidence",
          "source_family_purpose": "Deduplicate canonical event/episode membership sets by deterministic fingerprints and keep interval occurrences as separate references."
        }
      ]
    },
    {
      "id": "versioned-token-costs",
      "kind": "database pipeline and reader",
      "name": "Versioned token-cost projection",
      "purpose": "Apply explicit effective-dated operator price books to observed token categories and publish reusable snapshots with unpriced coverage visible.",
      "variants": [
        {
          "access": [
            "Retrieve committed source at the full revision using the frozen helper inventory.",
            "Operational use requires owner instructions, compatible environment and separately authorized artifact, database, service or provider access."
          ],
          "adoption_notes": [
            "Review entrypoint, caller, dependency and recorded limitations before extracting/adapting code. Preserve canonical owner and evidence boundaries.",
            "Branch labels and ancestry do not establish deployment or whole-capability equivalence."
          ],
          "atlas_asset_id": "capability-23-open-chat-reviewer-versioned-token-costs-04e35c78e40dbb81fd9f",
          "baseline_equivalence": "unknown",
          "baseline_relation": "diverged",
          "dependencies": [
            {
              "evidence": [
                {
                  "kind": "documentation",
                  "line": 24,
                  "path": "pyproject.toml",
                  "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc"
                }
              ],
              "name": "pydantic",
              "role": "Significant direct dependency, required runtime or owner interface; source slices and manifest declarations retained where inspected.",
              "version": ">=2.11",
              "version_kind": "constraint"
            },
            {
              "evidence": [
                {
                  "kind": "code",
                  "path": "src/chatreview/token_costs.py",
                  "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc"
                }
              ],
              "name": "Owner token_usage backfill and PostgreSQL session",
              "role": "Significant direct dependency, required runtime or owner interface; source slices and manifest declarations retained where inspected.",
              "version": null,
              "version_kind": "unknown"
            }
          ],
          "deployment": {
            "receipts": [],
            "status": "unknown"
          },
          "entrypoint_comparison": "identical-entrypoint-blob",
          "entrypoints": [
            "import_price_book(connection, data); build_token_costs(database_url); token_cost_report(connection, ...)"
          ],
          "evidence": [
            {
              "kind": "code",
              "line": 286,
              "line_end": 323,
              "note": "Agent-reviewed committed source slice retrieved with bundled helper; receipt retained.",
              "path": "src/chatreview/token_costs.py",
              "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
              "sha256": "c7ed9407dba7972131b01084d8a714f2ca1a432cbaaeb658eae26e08ffd0559f"
            },
            {
              "kind": "code",
              "line": 1,
              "line_end": 74,
              "note": "Agent-reviewed committed source slice retrieved with bundled helper; receipt retained.",
              "path": "src/chatreview/token_costs.py",
              "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
              "sha256": "c7ed9407dba7972131b01084d8a714f2ca1a432cbaaeb658eae26e08ffd0559f"
            },
            {
              "kind": "code",
              "line": 178,
              "line_end": 237,
              "note": "Agent-reviewed committed source slice retrieved with bundled helper; receipt retained.",
              "path": "src/chatreview/token_costs.py",
              "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
              "sha256": "c7ed9407dba7972131b01084d8a714f2ca1a432cbaaeb658eae26e08ffd0559f"
            }
          ],
          "id": "commit-6349f7f9784f057fd467c749d2439cdf9af331bc",
          "inputs": [
            "Owner token usage, explicit currency/rates by provider/model/tier/date and timezone"
          ],
          "limitations": [
            "Amounts are API-equivalent estimates, not subscription invoices. Missing rates remain unpriced rather than zero; no current provider prices were looked up.",
            "The report reader is read-only; price import and build/backfill write to the database. Current enabled price book and runtime deployment were not queried.",
            "Selected entry file is byte-identical to the frozen baseline. This is newly documented reuse, not a claim of branch-only novelty.",
            "Bounded source inspection only. No tests, models, owner programs, services, data reads/writes or deployments were run."
          ],
          "maturity": "unknown",
          "maturity_evidence": "Conservative source-only classification. Historical prototype status retained for review UI; owner maintenance and deployment not established.",
          "outputs": [
            "Price-book identity, token-cost snapshots, coverage and filtered cost reports"
          ],
          "retrieval_receipts": [
            {
              "line_from": 286,
              "line_to": 323,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/0b46a369a745eb9f2fc410f07222ae985ab4f2e4cd5965319488436c1e5d7f0d.json",
              "sha256": "d6d178ffc7ce4489cd6f74922dfd928bc086e59cb8f2f96905c20ca162f25505",
              "source_path": "src/chatreview/token_costs.py"
            },
            {
              "line_from": 1,
              "line_to": 17,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/34e68b58fef84b7cae78820ce6dc53a91e2e8b699cda83ff5dac84666b664fcd.json",
              "sha256": "a8d702182604f0ee2bfade4bc5078b5056f76a1711992ae1788bfdf35fcb8224",
              "source_path": "AGENTS.md"
            },
            {
              "line_from": 23,
              "line_to": 25,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/736e42e75aa36c05dc3db04c0c1692df0ce8b75119072c13d1f40ee5f86814c1.json",
              "sha256": "4d1db2f71d7532f9fbf3f8fdc66bc22e68d7fcdefe601b7639bb37608923f750",
              "source_path": "pyproject.toml"
            },
            {
              "line_from": 1,
              "line_to": 26,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/945d27012245583d48829fcf22b70baa4da27e03812a42d62f256c634d06877d.json",
              "sha256": "765b3d94d47390ba8f80d95be3f9f9732e36a424f845c8895b24968ccc9f2780",
              "source_path": "README.md"
            },
            {
              "line_from": 1,
              "line_to": 74,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/9b132755e1914c2011578a37b8b4e5a4c61598d88ef9d6ce289721d34adbb5e0.json",
              "sha256": "c484bb1d307b2dfbe892abdf037bc604aaf01a0bce6346edc0fb8c7d8a2e1d88",
              "source_path": "src/chatreview/token_costs.py"
            },
            {
              "line_from": 178,
              "line_to": 237,
              "path": "docs/capability-audits/reuse-priority/2026-10-15/reads/d9e7a87d17c32afb6bbfffd4b97523e35d67e5584362c6b3d0ae2e2fdc543612.json",
              "sha256": "ecc8296bf4879f135cb1f7b3a758eb42e226324c0d20e5998afeefb95ef23735",
              "source_path": "src/chatreview/token_costs.py"
            }
          ],
          "reuse_assessment": {
            "schema": "canetoad-reuse/v1",
            "category": "owner-interface",
            "work_needed": [
              "adapter",
              "access",
              "documentation",
              "verification"
            ],
            "effort": "large",
            "target_use": "A ChatReviewer observability consumer that reads immutable token-cost snapshots through the read-only /api/token-costs/status, summary, daily and sessions endpoints while preserving price-book and coverage provenance.",
            "next_step": "Define and publish the read-only consumer contract plus the required owner migration/token-usage prerequisites, then connect one dashboard or atlas view without duplicating price-book imports, backfills or snapshot writes.",
            "success_check": "A disposable consumer can retrieve one completed snapshot and verify its snapshot key, currency, active/original price-book versions, timezone and priced/unpriced coverage; GET requests perform no schema creation, backfill or snapshot build.",
            "basis": "The module combines Pydantic price-book validation, PostgreSQL tables from migration 0016, token-usage backfill, repeatable-read snapshot publication, freshness checks and filtered API reports. Documentation states that amounts are API-equivalent estimates, missing rates remain unpriced and Claude is the supported provider first. Those owner schemas and access requirements make this a strong interface reference but a multi-system reuse effort, and no runtime/database access was checked.",
            "assessed_at": "2026-10-15",
            "confidence": "high",
            "evidence": [
              {
                "path": "src/chatreview/token_costs.py",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "line": 1,
                "line_end": 360,
                "kind": "code",
                "sha256": "c7ed9407dba7972131b01084d8a714f2ca1a432cbaaeb658eae26e08ffd0559f",
                "note": "Pinned helper read; receipt reads-local/reads/8bf69317e1430785bcc32cfefcfdbd54c6e492216ad8ca250f7e1e7c55d44268.json."
              },
              {
                "path": "src/chatreview/migrations/0016_token_costs.sql",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "line": 1,
                "line_end": 30,
                "kind": "code",
                "sha256": "9c94dfa32e0f8cbd1e988b04b897327e29ca30d1299aea942930f07ee8834d80",
                "note": "Pinned schema read; receipt reads-local/reads/87dd5c5375880d38479b34813df876e0f169e6f929900e99a482d6b3a6b686c9.json."
              },
              {
                "path": "src/chatreview/api.py",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "line": 1138,
                "line_end": 1158,
                "kind": "code",
                "sha256": "e5fb96813559743598e6821162e24c3bb7c9c9d3dfeae715464da95acf14e5c7",
                "note": "Pinned read-only API boundary read; receipt reads-local/reads/862b2fa4a910ab3b307d73e698136a8a16cab4dc7b9020600f2408c7f4692ebc.json."
              },
              {
                "path": "docs/TOKEN_COSTS.md",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "line": 1,
                "line_end": 147,
                "kind": "documentation",
                "sha256": "0b1908d1283f8fb3a655f085bc242aefe8ee2a3d2b18f75d3edca2434014a6df",
                "note": "Pinned operation/limitation contract read; receipt reads-local/reads/b0251a649318d076239cd4aa66cb3f894ac8ba8c86ece4b2bc2442b8cf037aa6.json."
              },
              {
                "path": "pyproject.toml",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "line": 19,
                "line_end": 27,
                "kind": "documentation",
                "sha256": "25e16500bb9c2a73af68bd7da50a72dbdb6c164e9f6fb03a7782f6ff6d40e26d",
                "note": "Pinned dependency constraint read; receipt reads-local/reads/b235e3a50d236ce160b43c81813155805f8fa524c7ca76a1e1901360472dd46f.json."
              }
            ]
          },
          "runtime": {
            "receipts": [],
            "status": "not-checked"
          },
          "source": {
            "refs": [
              "refs/heads/codex/token-cost-projection",
              "refs/remotes/origin/codex/token-cost-projection"
            ],
            "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
            "working_changes": null,
            "worktree": null
          },
          "source_audit": {
            "baseline": {
              "ref": "refs/remotes/origin/main",
              "revision": "7b0806823e749873803d350618609226e6fcbe04",
              "selection_evidence": "Locally cached default or conventional ref; remote freshness and deployment unknown."
            },
            "checked_at": "2026-10-15",
            "coverage": [
              {
                "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
                "ref": "refs/heads/codex/archive-storage",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/private-archive-compat",
                "remote_freshness": "not-applicable",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "not-applicable",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
                "ref": "refs/heads/codex/token-cost-projection",
                "remote_freshness": "not-applicable",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/codex/worker-15min",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/heads/docs/recall-skill-refresh-20261014",
                "remote_freshness": "not-applicable",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "partial"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/heads/fix/bounded-refresh-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "partial"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/heads/fix/compact-recall-20261013",
                "remote_freshness": "not-applicable",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/fix/idle-database-churn-20261007",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/heads/main",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/heads/maintenance/repo-health-20261013",
                "remote_freshness": "not-applicable",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/remotes/origin/HEAD",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
                "ref": "refs/remotes/origin/codex/archive-storage",
                "remote_freshness": "unknown",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/private-archive-compat",
                "remote_freshness": "unknown",
                "revision": "0c4ccbfe86e7bdcf1ff84c5660021e2ed98b68b4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/review-dependency-upgrades-20260907",
                "remote_freshness": "unknown",
                "revision": "08a18a5f9da61b253183eff4d21eb515326a14c3",
                "state": "skipped"
              },
              {
                "reason": "Selected implementation/caller/dependency slices reviewed in this round; most branch files uninspected.",
                "ref": "refs/remotes/origin/codex/token-cost-projection",
                "remote_freshness": "unknown",
                "revision": "6349f7f9784f057fd467c749d2439cdf9af331bc",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/codex/worker-15min",
                "remote_freshness": "unknown",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "8c1dadc2aeeef60022a346ed77aae12e450040fb",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "141efe84ae5068dec98d28a7427458e8c4468228",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-13a777b093",
                "remote_freshness": "unknown",
                "revision": "11a5e5c62412875a4c20b1bb3b02ca50651ff407",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/bun/web/web-minor-and-patch-3457e10658",
                "remote_freshness": "unknown",
                "revision": "796791c5604f660dd02281709f958746974330d1",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-03db81fe05",
                "remote_freshness": "unknown",
                "revision": "661b22c4b41ddefd10386d5ada86a6ece7c6d4a2",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/github_actions/actions-2514a98571",
                "remote_freshness": "unknown",
                "revision": "cf7a89c7c7231e5f57e03c2437fcf7dd14501828",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/jsdom-30.0.1",
                "remote_freshness": "unknown",
                "revision": "2024029bd0939a2f7bf1b2edf7d1a181b2a1314f",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/lucide-react-1.37.0",
                "remote_freshness": "unknown",
                "revision": "e905acafa5bcaedcdf9dbe539879b37ea2023edb",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/testing-library/jest-dom-7.0.1",
                "remote_freshness": "unknown",
                "revision": "e1c3295c90021cd73c513e4ffe076a6986bbf253",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vite-8.2.2",
                "remote_freshness": "unknown",
                "revision": "2bade23ace71fb47b7273185466aedc317b82966",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/npm_and_yarn/web/vitest-4.1.11",
                "remote_freshness": "unknown",
                "revision": "f743dafa78068d7006d95e39d690d3edbfcad23e",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/pip/mcp-gte-1.12-and-lt-3",
                "remote_freshness": "unknown",
                "revision": "934cb7738cf8bf49fc6e1317dcabdafdb1452418",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/pip/uv-build-gte-0.8.0-and-lt-0.13",
                "remote_freshness": "unknown",
                "revision": "760b245daa7e818200b3c508849323fa86390351",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/dependabot/uv/pyjwt-2.15.0",
                "remote_freshness": "unknown",
                "revision": "e1db24b75800eef8040e797071c550c9c1bf3842",
                "state": "skipped"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/remotes/origin/docs/recall-skill-refresh-20261014",
                "remote_freshness": "unknown",
                "revision": "198143467bf854501420bf89a39eb96fa2fcc219",
                "state": "partial"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/remotes/origin/fix/bounded-refresh-health-20261013",
                "remote_freshness": "unknown",
                "revision": "4ae80fda8188e71ffc1b15c5e38f9a43190dd9da",
                "state": "partial"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/remotes/origin/fix/compact-recall-20261013",
                "remote_freshness": "unknown",
                "revision": "046d85ac80f6246a04e88390f49cc81c6c89b43b",
                "state": "partial"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/remotes/origin/main",
                "remote_freshness": "unknown",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/maintenance/repo-health-20261013",
                "remote_freshness": "unknown",
                "revision": "006c4d91d0aa408f683ea12d06c17c1f66a1f1b0",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-20",
                "remote_freshness": "unknown",
                "revision": "88f3ebe08f08a70575208ef6b72bd6289bcc6f4d",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-21",
                "remote_freshness": "unknown",
                "revision": "757a81942bc46b50655584b0553fad7cdc418db1",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-22",
                "remote_freshness": "unknown",
                "revision": "b2f4a2b9afc264ec4b3a884edd5ec7e25fcf15b3",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-23",
                "remote_freshness": "unknown",
                "revision": "18059bd59bb7833af6ab09b4a8218f5f2f08a3ac",
                "state": "skipped"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/remotes/origin/review-9",
                "remote_freshness": "unknown",
                "revision": "35f2eefc639da6e2075d2e7cadd8f84f8d360177",
                "state": "skipped"
              },
              {
                "reason": "Source revision represented by an earlier imported capability snapshot; no whole-branch claim.",
                "ref": "refs/tags/recall-skill-20261014",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "partial"
              },
              {
                "reason": "Inventoried only; source inspection pending.",
                "ref": "refs/tags/v0.1.0-alpha.1",
                "remote_freshness": "not-applicable",
                "revision": "b027ccae1c42a87bbf5b81e1a4280de7e81ba77f",
                "state": "skipped"
              },
              {
                "reason": "Location/HEAD inventoried; working files excluded.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "7b0806823e749873803d350618609226e6fcbe04",
                "state": "skipped"
              },
              {
                "reason": "Location/HEAD inventoried; working files excluded.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/archive-storage/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "3c0116952296b57951210d0a843ce13f44ce576c",
                "state": "skipped"
              },
              {
                "reason": "Location/HEAD inventoried; working files excluded.",
                "ref": "worktree:${SOURCE_HOME}/.codex/worktrees/public-chatreview-deploy/23-open-chat-reviewer",
                "remote_freshness": "not-applicable",
                "revision": "a60192a348356bbe3450b5525d90e4e28512f1f4",
                "state": "skipped"
              },
              {
                "reason": "Location/HEAD inventoried; working files excluded.",
                "ref": "worktree:${SOURCE_HOME}/Documents/23-open-chat-reviewer-energy-fix",
                "remote_freshness": "not-applicable",
                "revision": "b121debffb0f59268bd437b40dd691a75b2d9245",
                "state": "skipped"
              }
            ],
            "document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/reuse-priority/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
            "document_sha256": "6314ede0f45b3dd9541229214557429a7d79ec579e0a29e4324135bafa6d8641",
            "limitations": [
              "Central snapshot only; not installed in owner repository.",
              "Sixteen selected previously uninspected tips across thirteen repositories; not an exhaustive audit.",
              "Inventory capture time is retained from the previous round; no fetch or current-ref assertion.",
              "Retrieval receipts prove retrieval, not complete review."
            ],
            "method": "Bundled helper source reads against the unchanged branch-continuation frozen inventory, followed by interpretation of selected implementation/caller/dependency slices and exact entry-file comparisons."
          },
          "source_family_document_path": "${SOURCE_HOME}/Documents/36-canetoad-data-atlas/docs/capability-audits/reuse-priority/2026-10-15/repositories/23-open-chat-reviewer/CAPABILITIES.md",
          "source_family_name": "Versioned token-cost projection",
          "source_family_purpose": "Apply explicit effective-dated operator price books to observed token categories and publish reusable snapshots with unpriced coverage visible."
        }
      ]
    },
    {
      "id": "opencode-sqlite-ingestion",
      "name": "OpenCode SQLite conversation ingestion",
      "purpose": "Add local and remote OpenCode conversation evidence to the shared chat archive without modifying OpenCode inputs.",
      "kind": "pipeline",
      "variants": [
        {
          "id": "working-opencode-sqlite-20261026",
          "source": {
            "revision": "7b0806823e749873803d350618609226e6fcbe04",
            "refs": [
              "refs/heads/main"
            ],
            "worktree": null,
            "working_changes": [
              {
                "path": "src/chatreview/providers/opencode.py",
                "sha256": "161bd66e23dd3546eb9049d1bdd5c262fc18ed5bb837fb8d9873db5b10bf87a1",
                "untracked": true
              },
              {
                "path": "src/chatreview/providers/__init__.py",
                "sha256": "39033182a674b98939124491678ffce2b7f8fb38335dda0d6cf386b93a1ea59f",
                "untracked": false
              },
              {
                "path": "src/chatreview/config.py",
                "sha256": "60bb548b9ce8b43e702701012fc71f181d1426497d145e36aed4d14ec7a72f21",
                "untracked": false
              },
              {
                "path": "src/chatreview/source_roots.py",
                "sha256": "cc76227cc61638b3721439447471b0d738f56ae243b0e95fb9eb4feaea7a8fff",
                "untracked": false
              },
              {
                "path": "src/chatreview/ingest.py",
                "sha256": "0cfee717a2a02a7a322c271c34dcc573a605844e212daa6e2687331d8b8fd976",
                "untracked": false
              },
              {
                "path": "src/chatreview/cli.py",
                "sha256": "5767d3fac97f1b05480cb11172bdb459820ad4327633284c957dc6d373d8d11b",
                "untracked": false
              },
              {
                "path": "src/chatreview/api.py",
                "sha256": "8aaf6ead07076a1d34bbdbb2ea275789a9d71dffe7ffd304635c9acd9a6b596b",
                "untracked": false
              },
              {
                "path": "src/chatreview/setup_jobs.py",
                "sha256": "20eaa141cdb722bf9f6569ecd88024f9c746b4d770d256b75f843c9e319725bb",
                "untracked": false
              },
              {
                "path": "src/chatreview/setup_planner.py",
                "sha256": "e4e89c0a203217d5cb6d9ffb722d14c8a238dc4bbe94f525397c1e32d02ceb40",
                "untracked": false
              },
              {
                "path": "src/chatreview/source_selection.py",
                "sha256": "14b8f138c24c54a2da32b45cede4fc087435528b3bae67bcce0d20d3764ac4b2",
                "untracked": false
              },
              {
                "path": "tests/test_opencode.py",
                "sha256": "4cd364f75ae93912a0a4a29d838357add25a028be7513a9e1ae2d9630374ebf4",
                "untracked": true
              },
              {
                "path": "scripts/chatreview-sync.sh",
                "sha256": "d8fb0e56d19f08866ab8b6e588b58cbaeb74fe4c6d2e71135754a928f7feb782",
                "untracked": false
              },
              {
                "path": "scripts/connect-computer.sh",
                "sha256": "db2bd5a566a966ab9b83511d0e11d851cd9aafe2ecc4bc0274c18a5b46e5dc9c",
                "untracked": false
              },
              {
                "path": "scripts/create-writer-config.sh",
                "sha256": "e02d58efde194589e42f3bc643a5990dd8b5d839ab3009285f827dd482291a14",
                "untracked": false
              },
              {
                "path": "web/src/components/Common.tsx",
                "sha256": "eb16def4215a960faf91e6318ba49506b4335a211f6640b8284bb8c177ba66e5",
                "untracked": false
              },
              {
                "path": "web/src/pages/SourceRootEditor.tsx",
                "sha256": "ec193b0b808cc160cc81a19308223b3d6d9648b19d3b094809da1eea14f881a3",
                "untracked": false
              },
              {
                "path": "web/src/pages/SetupPage.tsx",
                "sha256": "b04412069254654293f7b90b24dba4f0fce567c799e1f304f536b52b1c3b7f49",
                "untracked": false
              },
              {
                "path": "web/src/pages/SetupRoute.tsx",
                "sha256": "91964031534eb6cc08497d7d28fd5ab4218188a182b51d483dbc5134a377e022",
                "untracked": false
              },
              {
                "path": "docs/ARCHITECTURE.md",
                "sha256": "abd24bd4963d000cbe6f19a7db25eb6626ecd35f0dc43751d6bc11890ff90325",
                "untracked": false
              },
              {
                "path": "docs/TAILSCALE_MULTI_MACHINE.md",
                "sha256": "221fb2efaeba825f8c3ec41e797f597c8b1f583624823465886f4128262e519a",
                "untracked": false
              }
            ]
          },
          "baseline_relation": "same-tip",
          "baseline_equivalence": "absent",
          "maturity": "experimental",
          "entrypoints": [
            "OpenCodeAdapter.prepare/discover/parse_many",
            "scripts/chatreview.sh sync --provider opencode --no-git --opencode-root <data-folder>",
            "CHATREVIEW_OPENCODE_ROOT / CHATREVIEW_OPENCODE_ROOTS",
            "Setup source roots and provider selector; scripts/chatreview-sync.sh on existing writers"
          ],
          "inputs": [
            "Read-only OpenCode opencode.db session/message/part tables, including committed WAL data",
            "Machine identity and PostgreSQL archive configuration"
          ],
          "outputs": [
            "Deterministic private per-session JSON row exports and catalog",
            "Raw PostgreSQL revisions with database/session provenance",
            "Canonical message, reasoning and tool fragments for existing session, trace and lexical search interfaces"
          ],
          "dependencies": [
            {
              "name": "Python sqlite3 / fcntl",
              "role": "Read-only consistent SQLite snapshots and local export locking",
              "version": null,
              "version_kind": "unknown",
              "evidence": [
                {
                  "path": "src/chatreview/providers/opencode.py",
                  "sha256": "161bd66e23dd3546eb9049d1bdd5c262fc18ed5bb837fb8d9873db5b10bf87a1",
                  "untracked": true,
                  "kind": "code",
                  "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
                }
              ]
            },
            {
              "name": "PostgreSQL / existing ingestion core",
              "role": "Runtime authority, raw revisions, canonical events and search",
              "version": null,
              "version_kind": "unknown",
              "evidence": [
                {
                  "path": "src/chatreview/ingest.py",
                  "sha256": "0cfee717a2a02a7a322c271c34dcc573a605844e212daa6e2687331d8b8fd976",
                  "untracked": false,
                  "kind": "code",
                  "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
                }
              ]
            }
          ],
          "access": [
            "Local read access to the selected OpenCode data directories",
            "CHATREVIEW_DATABASE_URL and stable distinct CHATREVIEW_MACHINE_ID; existing writer credentials can be reused",
            "Tailscale reachability for remote writers; no writer migrations"
          ],
          "evidence": [
            {
              "path": "src/chatreview/providers/opencode.py",
              "sha256": "161bd66e23dd3546eb9049d1bdd5c262fc18ed5bb837fb8d9873db5b10bf87a1",
              "untracked": true,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "src/chatreview/providers/__init__.py",
              "sha256": "39033182a674b98939124491678ffce2b7f8fb38335dda0d6cf386b93a1ea59f",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "src/chatreview/config.py",
              "sha256": "60bb548b9ce8b43e702701012fc71f181d1426497d145e36aed4d14ec7a72f21",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "src/chatreview/source_roots.py",
              "sha256": "cc76227cc61638b3721439447471b0d738f56ae243b0e95fb9eb4feaea7a8fff",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "src/chatreview/ingest.py",
              "sha256": "0cfee717a2a02a7a322c271c34dcc573a605844e212daa6e2687331d8b8fd976",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "src/chatreview/cli.py",
              "sha256": "5767d3fac97f1b05480cb11172bdb459820ad4327633284c957dc6d373d8d11b",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "src/chatreview/api.py",
              "sha256": "8aaf6ead07076a1d34bbdbb2ea275789a9d71dffe7ffd304635c9acd9a6b596b",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "src/chatreview/setup_jobs.py",
              "sha256": "20eaa141cdb722bf9f6569ecd88024f9c746b4d770d256b75f843c9e319725bb",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "src/chatreview/setup_planner.py",
              "sha256": "e4e89c0a203217d5cb6d9ffb722d14c8a238dc4bbe94f525397c1e32d02ceb40",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "src/chatreview/source_selection.py",
              "sha256": "14b8f138c24c54a2da32b45cede4fc087435528b3bae67bcce0d20d3764ac4b2",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "tests/test_opencode.py",
              "sha256": "4cd364f75ae93912a0a4a29d838357add25a028be7513a9e1ae2d9630374ebf4",
              "untracked": true,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "scripts/chatreview-sync.sh",
              "sha256": "d8fb0e56d19f08866ab8b6e588b58cbaeb74fe4c6d2e71135754a928f7feb782",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "scripts/connect-computer.sh",
              "sha256": "db2bd5a566a966ab9b83511d0e11d851cd9aafe2ecc4bc0274c18a5b46e5dc9c",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "scripts/create-writer-config.sh",
              "sha256": "e02d58efde194589e42f3bc643a5990dd8b5d839ab3009285f827dd482291a14",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "web/src/components/Common.tsx",
              "sha256": "eb16def4215a960faf91e6318ba49506b4335a211f6640b8284bb8c177ba66e5",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "web/src/pages/SourceRootEditor.tsx",
              "sha256": "ec193b0b808cc160cc81a19308223b3d6d9648b19d3b094809da1eea14f881a3",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "web/src/pages/SetupPage.tsx",
              "sha256": "b04412069254654293f7b90b24dba4f0fce567c799e1f304f536b52b1c3b7f49",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "web/src/pages/SetupRoute.tsx",
              "sha256": "91964031534eb6cc08497d7d28fd5ab4218188a182b51d483dbc5134a377e022",
              "untracked": false,
              "kind": "code",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "docs/ARCHITECTURE.md",
              "sha256": "abd24bd4963d000cbe6f19a7db25eb6626ecd35f0dc43751d6bc11890ff90325",
              "untracked": false,
              "kind": "documentation",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            },
            {
              "path": "docs/TAILSCALE_MULTI_MACHINE.md",
              "sha256": "221fb2efaeba825f8c3ec41e797f597c8b1f583624823465886f4128262e519a",
              "untracked": false,
              "kind": "documentation",
              "note": "Reviewed OpenCode collection, configuration, callers, or regression checks."
            }
          ],
          "deployment": {
            "status": "not-deployed",
            "receipts": [],
            "note": "Running central service inspected on 2026-10-26 still uses pinned release 6c09d7d; one-off import used reviewed working code."
          },
          "runtime": {
            "status": "demonstrated",
            "checked_at": "2026-10-26",
            "receipts": [
              ".chatreview/opencode-verification.json (private local receipt, not published)",
              ".chatreview/opencode-repeat.log (private local receipt, not published)"
            ],
            "note": "Local import: 977 sessions, 6706 messages, 27270 parts; all row hashes matched; repeat skipped all 977 sources. Live session and lexical search HTTP reads returned results. Python and UI checks passed. Mac execution not demonstrated."
          },
          "limitations": [
            "Current SQLite layout only; legacy JSON storage unsupported",
            "Diagnostic logs, credentials, backups and snapshot repositories excluded",
            "Bounded history selection conservatively includes full OpenCode sessions",
            "Byte offsets identify generated row exports, not original SQLite pages",
            "Existing explicit source-root files keep the new provider disabled until configured; explicit CLI override applies to one invocation",
            "Raw parts are retained completely; text/reasoning/tool/file parts are projected, other part types remain raw evidence",
            "No additional packages or model invocations introduced; current Mac execution and automatic central deployment remain unverified"
          ],
          "adoption_notes": [
            "Pull this source change, run uv sync --locked, and reuse the existing writer configuration.",
            "Use documented Mac command with --opencode-root for first sync; persist the root separately for future scheduled runs."
          ]
        }
      ]
    }
  ],
  "repository": {
    "checkout_path": "${SOURCE_HOME}/Documents/23-open-chat-reviewer",
    "id": "23-open-chat-reviewer",
    "name": "23-open-chat-reviewer",
    "origin": "https://github.com/MiddleDistances/23-open-chat-reviewer"
  },
  "schema": "canetoad-capabilities/v1"
}
```

OpenCode was reviewed as working source on 2026-10-26; hashes identify that snapshot before commit. Historical local home paths are represented by `${SOURCE_HOME}` for public portability. No prior variant or coverage record was removed.
