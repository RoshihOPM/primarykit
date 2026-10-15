# System architecture review checklist

- Contracts: public endpoints, versioning, authorization, pagination, filtering, request idempotency, error schema.
- Modularity: one owner per domain rule, dependency direction, no cyclic imports, no client-specific imports in shared Apps.
- Consistency: invariants, transaction boundaries, external side effects, retry safety and duplicate delivery.
- Security: tenant and object scoping, enumeration/IDOR, least privilege, secrets, upload validation, abuse limits.
- Performance: likely cardinalities, p95 SLO, query count, pool sizing, indexes, cache invalidation.
- Reliability: readiness, liveness, backups, restore drills, migration rollback/forward plan, alerting and logs.
- Delivery: smallest safe version, test pyramid, review gates, measurable success criteria.

## ADR short template

`docs/adr/NNNN-title.md`:
- Context and constraints
- Decision
- Options and trade-offs
- Consequences and migration plan
- Verification and reversibility
