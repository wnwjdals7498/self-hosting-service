# deployments/

This directory is **retained as-is from upstream Plane** (enterprise /
community deployment templates: `aio/`, `cli/`, `kubernetes/`, `swarm/`).
The templates still reference the original Postgres (`plane-db`) service
and the legacy `DATABASE_URL` / `POSTGRES_*` environment variables.

**This fork does not deploy from `deployments/`.** The SQLite migration
documented in `docs/customization/sqlite-migration/` replaced the DB
backend for the 1-person workspace use case. Deployment instructions for
this fork live in `docs/customization/plan.md` and the `docs/customization/plan/`
step files, which target SQLite + the stripped-down `docker-compose.yml`
at the repo root (no `plane-db` service).

If you need to re-enable a Postgres deployment path, do so in the
customization docs first; don't reach for the files here until the
rollback is intentional. See `docs/customization/sqlite-migration/phase-g-cleanup.md`
for the rationale behind dropping Postgres from the active runtime.
