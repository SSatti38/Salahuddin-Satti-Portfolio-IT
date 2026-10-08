# Security SaaS Design Proposals

Three separate portfolio concepts, organized by category and exact project name. **Each is a design proposal, not an implemented or production-ready service.** The mockups are static, self-contained interfaces with synthetic data; they make no live provider, backend, AI, or customer-data connections. Test plans and standards/research context are proposed design artifacts, not completed test results or compliance evidence.

The existing paths are intentionally retained: `security-operations/TriageSignal/`, `identity-governance/AccessAtlas/`, and `telemetry-resilience/LogPulse/`.

## TriageSignal — Security Operations

Evidence-first alert triage for SOC analysts. The proposal keeps source facts distinct from advisory interpretation and leaves every decision to a human.

**Design:** [Landing README and software design](security-operations/TriageSignal/README.md). **Diagrams:** [architecture](security-operations/TriageSignal/diagrams/architecture.mmd) · [trust boundaries](security-operations/TriageSignal/diagrams/trust-boundaries.mmd). **Prototype:** [local mockup source](security-operations/TriageSignal/prototype/index.html) · [published mockup route](https://ssatti38.github.io/Salahuddin-Satti-Portfolio-IT/projects/security-operations/TriageSignal/prototype/).

**Testing plan (proposed, not executed):** [quality and verification strategy](security-operations/TriageSignal/README.md#reliability-operations-and-quality). **Research context:** inline source links in [advisory AI and human review](security-operations/TriageSignal/README.md#advisory-ai-and-human-review), [privacy and audit](security-operations/TriageSignal/README.md#privacy-retention-encryption-and-audit), and [reliability and quality](security-operations/TriageSignal/README.md#reliability-operations-and-quality).

**Status:** Design document and local-only synthetic prototype; no backend, connectors, model calls, or executable application tests.

## AccessAtlas — Identity Governance

A read-only access-review workspace for identity and entitlement snapshots. Reviewers record decisions; connected identity providers remain untouched.

**Design:** [Landing README and software design](identity-governance/AccessAtlas/README.md). **Diagrams:** [architecture](identity-governance/AccessAtlas/diagrams/architecture.mmd) · [trust boundaries](identity-governance/AccessAtlas/diagrams/trust-boundaries.mmd). **Prototype:** [local mockup source](identity-governance/AccessAtlas/prototype/index.html) · [published mockup route](https://ssatti38.github.io/Salahuddin-Satti-Portfolio-IT/projects/identity-governance/AccessAtlas/prototype/).

**Testing plan (proposed, not executed):** [evidence, backup, testing, and deployment](identity-governance/AccessAtlas/README.md#evidence-backup-testing-and-deployment). **Research context:** inline source links in [audience and value](identity-governance/AccessAtlas/README.md#audience-problem-and-value), [integrations and least privilege](identity-governance/AccessAtlas/README.md#integrations-and-least-privilege), [tenant separation and authorization](identity-governance/AccessAtlas/README.md#tenant-separation-schema-and-authorization), and [encryption and session controls](identity-governance/AccessAtlas/README.md#encryption-identity-and-session-controls).

**Status:** Design document and local-only synthetic prototype; no backend, provider integrations, or executable application tests.

## LogPulse — Telemetry Resilience

A source-health and visibility-evidence concept focused on freshness, parsing, buffering, and mapping—not detection execution or incident response.

**Design:** [Landing README and software design](telemetry-resilience/LogPulse/README.md). **Diagrams:** [source-to-health flow](telemetry-resilience/LogPulse/diagrams/architecture.mmd) · [trust boundaries](telemetry-resilience/LogPulse/diagrams/trust-boundaries.mmd). **Prototype:** [local mockup source](telemetry-resilience/LogPulse/prototype/index.html) · [published mockup route](https://ssatti38.github.io/Salahuddin-Satti-Portfolio-IT/projects/telemetry-resilience/LogPulse/prototype/).

**Testing plan (proposed, not executed):** [testing, deployment, and roadmap](telemetry-resilience/LogPulse/README.md#testing-deployment-and-roadmap). **Research context:** inline source links in [the design rationale](telemetry-resilience/LogPulse/README.md#who-it-is-for-and-what-it-solves), [architecture and taxonomy notes](telemetry-resilience/LogPulse/README.md#proposed-architecture-and-data-flow), and [security and privacy](telemetry-resilience/LogPulse/README.md#security-tenancy-identity-and-privacy).

**Status:** Design document and local-only synthetic prototype; no forwarder, backend, integrations, or executable application tests.
