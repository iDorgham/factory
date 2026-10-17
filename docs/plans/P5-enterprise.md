# P5 — Enterprise Plan

**Phase:** P5
**Status:** ⬜ Planned
**Goal:** Verifiable audit trail plus kernel-enforced RBAC, hierarchical budgets, brand design systems, and compliance exports.

**Depends on:** [P4](P4-team.md). Needs a stable core first.

## Workstreams

### 1. Control plane and identity
- [ ] Identity from the organization's identity provider via a local control-plane component
- [ ] SSO integration; disk-level access to the factory tree restricted at the host level (the spec states this limit plainly — RBAC cannot govern raw file access)

### 2. RBAC
- [ ] Roles: Owner, Admin, Maintainer, Developer, Reviewer, Viewer
- [ ] Kernel checks permissions on **every** command
- [ ] Policy loosening below the preset requires Owner/Admin and is audited

### 3. Hash-chained audit
- [ ] `audit/audit.chain`: each entry includes the hash of the previous entry
- [ ] `factory audit verify` checks the chain end to end
- [ ] Periodic anchors: hash exported to an external system to detect wholesale rewrites
- [ ] Retention and export policy-controlled

### 4. Hierarchical budgets
- [ ] Job → epic → project → brand → month, with owner notifications and hard stops
- [ ] Burn-down and per-brand cost attribution in the dashboard

### 5. Brands and design systems
- [ ] `brands/<brand>/`: `brand.json` + design-system (`tokens.json`, `components/`, `docs.md`, `lint.json`)
- [ ] Design-system conformance as a **check**: token lint + component usage lint on UI diffs
- [ ] `design_system_required_before_products` dependency epic
- [ ] Design-system pipeline stages: Brand Audit → Definition → Tokens → Core Components → Docs & Preview → Accessibility & Theming (dark mode, contrast, RTL, reduced motion) → Packaging & Versioning → Adoption
- [ ] Multi-brand isolation: projects, skills, memory, budgets scoped to a brand; cross-brand sharing explicit

### 6. Compliance
- [ ] Exportable evidence bundles per release: checks, approvals, SBOM, license scan, audit extract
- [ ] Change windows and freeze periods enforced by policy
- [ ] Data residency and model-provider restrictions as policy fields enforced at adapter selection

## Exit criteria

- The audit chain verifies end to end and RBAC is kernel-enforced (spec success criterion #8).
- An operator can produce a compliance evidence bundle for a release from the dashboard/CLI.
- Brand design-system lint runs on every UI diff in brand-scoped projects.
