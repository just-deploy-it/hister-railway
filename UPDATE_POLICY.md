# Update policy

The scheduled updater checks GitHub's latest stable Hister release daily and resolves its official GHCR tag to an immutable OCI digest.

Before an update reaches `main`, the updater must:

1. Advance `Dockerfile`, `upstream.json` and `railway-template.json` from their current shared pin.
2. Run the two-consecutive-update regression test and fail-closed configuration checks.
3. Confirm the Dockerfile default equals the tested candidate image.
4. Clean-build that exact image with the candidate digest passed explicitly.
5. Commit and push only after every gate passes.

Post-push CI repeats the tests, configuration checks and clean image build. Hister releases are potentially breaking because its configuration and index formats can evolve. Back up `/hister/data` before a production upgrade and keep the prior immutable digest available for rollback.
