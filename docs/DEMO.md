# Trace: submission and demo

## Pitch

Trace gives an agent the ability to find online appearances of character artwork and return a permission-aware, reviewable trail of evidence.

## The job

A character-IP owner needs to locate relevant appearances, distinguish known permissions from unresolved usage, and prepare the next action without repeatedly reconstructing the context. Discovery alone produces links; Trace connects links to reference artwork, owner decisions, and scoped permission records.

## Three-minute demonstration

1. Open **Overview** and click **Explore the Orbit demo**. State explicitly that Orbit is original demo artwork and all six listings are fictional. This demonstrates the connected workflow, not live marketplace coverage.
2. In **Discovery**, show the reference, source coverage, and six candidate appearances grouped into five distinct images. A shirt appears twice; the official print has a scoped permission record. A different blue rabbit remains unverified.
3. Open the shirt. Compare its image against the reference, inspect the fingerprint evidence, and explain why priority reflects review urgency rather than estimated financial loss.
4. Open the blue rabbit, record **Not a match**, and run discovery again. The identical-image correction is reused; the rabbit no longer needs the same identity review. This proves exact-image memory, not recognition of unseen drawings.
5. In **Licensing**, record a Moon Market request for `moon-market.example`, category `apparel`, territory `US`, and a date range including today. The pending request creates no permission. Click **Record approval** to record an owner-supplied approval.
6. Return to **Discovery**. The matching shirt scope now has a permission record. Other categories, territories, domains, and unknown context remain unresolved.
7. Export the shirt's evidence ZIP. Show `case.json`, `candidate.png`, reference artwork, the capture digest, review history, and `REVIEW.md`.
8. Open **Agent tools** and inspect live schemas. `npm run test:mcp` demonstrates an official SDK client starting discovery, recording an owner-directed review, and downloading evidence.

## Live discovery

Click **Try a live public example** on Overview, then search **Public collections**. This searches actual Wikimedia Commons and Openverse results and fetches candidate images. It does not demonstrate broad commercial marketplace coverage. Fetch failures are retained as unverified candidates.

For broader reverse-image discovery, configure Google Vision or SerpAPI. Those integrations require working provider credentials. Uploaded private references work with Google; Lens requires a public image URL. Optional Gemini review compares different depictions but is separate from copy matching.

## Technical substance

Supabase Auth owns the workspace; Postgres retains characters, scans, findings, inquiries, grants, and review history; private Storage contains artwork and captures; Realtime publishes search changes; RLS and composite ownership foreign keys isolate users. Fetching validates public addresses and pins connections to those addresses, rechecking every redirect. REST and MCP use the same authenticated workflow services.

## Claim the prototype can prove

An owner can move from references to a documented review decision, and identical-image feedback can prevent repeating an identity review. Browser tests verify discovery, feedback reuse, approval scope, evidence downloads, persistence, and mobile layout. Live stack tests check private Storage and cross-workspace access.

It cannot establish customer willingness to pay, litigation recovery, exhaustive coverage, or recognition accuracy across unseen character depictions. Those require real user workflows and independent evaluation.
