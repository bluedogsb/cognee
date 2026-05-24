# PLATFORM_PATCHES.md

Platform-specific divergences from upstream `topoteretes/cognee` carried in
this fork (`bluedogsb/cognee`). Each entry lists the file, line range,
rationale, and introducing commit. **Read this file BEFORE any upstream
merge** — these locations need conflict-resolution care.

| File | Lines (post-patch) | Patch | Why | Introduced |
|---|---|---|---|---|
| `cognee-mcp/Dockerfile` | L36 | Adds `curl \` to apt install | In-container HTTP probing for ops/debug ('docker exec t440-cognee-mcp curl ...') | `a7335421` (2026-05-24) |
| `cognee/infrastructure/databases/vector/embeddings/OpenAICompatibleEmbeddingEngine.py` | L105-L125 (post-patch range; original L105-L112 expanded by +13 lines) | `COGNEE_EMBEDDING_NO_V1` env var to opt-out of `/v1` URL normalization. When set: strips trailing `/v1` then passes endpoint as-is to AsyncOpenAI base_url; SDK calls `{endpoint}/embeddings` (no `/v1` prefix). When unset/false: original upstream normalization unchanged. | Support OpenAI-compat embedding servers that serve `/embeddings` without `/v1` prefix (e.g. infinity-emb 0.0.77 — https://github.com/michaelfeil/infinity). Platform deployment needs this for cognee to talk to its existing infinity at DGX2:9303. | (Phase 8.4.2 — SHA filled in post-commit) |
| `cognee/tests/unit/infrastructure/test_openai_compatible_embedding_engine.py` | L91-L156 (post-patch range) | 2 existing tests gain `monkeypatch.delenv("COGNEE_EMBEDDING_NO_V1", ...)` for env-isolation; 2 new tests `test_endpoint_normalization_no_v1_true` + `test_endpoint_normalization_no_v1_strips_trailing_v1` lock the platform-patch behavior. | TDD lock for the env-var opt-out branches. | (Phase 8.4.2 — SHA filled in post-commit) |

## Upstream sync protocol

When merging upstream `topoteretes/cognee` into this fork:

1. `git fetch <upstream>` — note: as of 2026-05-24 NO `upstream` remote is
   configured. bluedogsb/cognee acts as the canonical fork that absorbs
   upstream PRs via the maintainer's own merge process (today's `git pull
   origin main` pulled 5 upstream PRs that landed since the last sync).
2. Before merging, `grep -rn "PLATFORM-PATCH (gamemagick)" .` to inventory
   current divergences in the working tree.
3. Read this file to know which conflicts are expected.
4. After merge: re-run static gate
   `agentic_workflows/scripts/deploy/tests/cognee/test_platform_patch_markers.sh`
   (in the platform repo) to verify markers still present.
5. Update the line-range columns in this file with any drift from the merge.
6. Update the introducing-commit column ONLY if a patch was re-applied to a
   different commit (e.g. if `git rebase` rewrote SHAs).

## Inline markers

Each patched location has an inline `# PLATFORM-PATCH (gamemagick
YYYY-MM-DD): ...` comment so reviewers/merge-resolvers see the divergence in
context. The static gate at `agentic_workflows/scripts/deploy/tests/cognee/test_platform_patch_markers.sh`
(in the platform repo) greps for that marker before any `bash
deploy_cognee_to_t440.sh deploy` so an accidental upstream sync that
clobbers the patch is caught at the deploy step.

## Related platform docs

- R1 brief: `agentic_workflows/docs/20260524/20260524_PHASE_8_4_2_COGNEE_EMBEDDING_PATH_FIX_R1_BRIEF.md`
  in the platform repo (`bluedogsb/flask-server`).
- Phase 8.4.1 (upstream half of the cognee `/api/v1/add` fix chain):
  `agentic_workflows/docs/20260524/20260524_PHASE_8_4_1_COGNEE_500_FIX_R1_BRIEF.md`.
- Investigation briefs (Agent A container root cause + Agent B upstream
  contract): `agentic_workflows/docs/20260524/20260524_COGNEE_500_AGENT_*.md`.
