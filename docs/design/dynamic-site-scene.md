# Dynamic site scene

## Runtime architecture

Worker and Facilitator share `web/components/SiteSceneExplorer.tsx`. A role page supplies only its heading and locale; neither page sends private worker data or legal decisions to the renderer. `web/lib/site-scene/registry.ts` is the allowlist of CC0 runtime GLBs. `configs.ts` supplies two explicitly synthetic fixtures. `provider.ts` defines the configuration-provider seam and the offline deterministic provider; every proposal is treated as untrusted JSON, checked for exact supported fields and geometry bounds, then passed through `assemble.ts` before the config can render.

The assembly function converts boundary size, footprint, bay grid, floor count/height, phase and layer flags into repeatable object placements. It uses Kenney floor, column and wall modules for the building; Kenney fences, barriers, cones and dumpster for site props; Kenney low-detail buildings for surrounding context; and low-poly primitives for roads, concrete beams, scaffold tubes and the tower crane. The kit contains no crane model, so the crane is an explicitly illustrative generated assembly. The renderer loads only registered GLB files, clones the meshes at validated transforms, supports camera orbit/pan/zoom/reset, mesh hover/click selection, floor filtering, layer visibility and an accessible object list. It caps configuration complexity, scales WebGL pixel ratio for mobile and disposes scene resources when the layout changes or the page unmounts.

The fixtures demonstrate the same code building a 3-floor 3×2-bay frame and a 6-floor 4×3-bay envelope. Their boundaries, structural spacing, floor heights and components are data. To add a supported fixture or an authorized configured site layout, provide a `SiteSceneConfig`; do not add geometry branches to the React renderer.

## Provenance and legal data

Both role pages currently use `SYNTHETIC_DEMO_GEOMETRY`. The backend's site fixtures contain plot area and activity facts but no surveyed boundary coordinates, building footprint, floor count or structural grid. A site ID, resolver result, worker Parchi and Facilitator permission do not supply those missing dimensions. Therefore, none is used to place scene objects. The layout selector labels both options illustrative, and the scene states that it is not a real site survey.

The scene engine has no legal-rule input and generates no restriction status. Its named sample areas have no legal meaning. The existing Supervisor 3D model remains a separate resolver-linked schematic; any status shown there continues to come from its resolver payload. No geometry, color, object name or model output changes compliance, workflow, evidence, consent or authorization.

Current data sources contain no authorized geometry API. To move from a synthetic fixture to `CONFIGURED_SITE_GEOMETRY` or `VERIFIED_SITE_GEOMETRY`, an authenticated backend must provide a validated source record and its geometry provenance first. `UNAVAILABLE` remains the correct display if that data cannot be loaded; it must not silently fall back while retaining a live-site label.

## Bedrock assessment

The AWS template's optional Bedrock grant and `BedrockModelId` are for the existing explanation adapters. Those adapters can rephrase a deterministic, already-computed explanation; they do not assemble site geometry. The default `ExplainBackend` is `deterministic`, and `.env.example` leaves `BEDROCK_MODEL_ID` empty. The IAM permission is conditional on selecting an explanation backend and a model ID. The application has no authorized geometry authoring endpoint or surveyed project data for a model to use.

Bedrock is not called for scene configuration. Deterministic layout selection needs no network, token budget, cold start or per-view charge. `SiteSceneConfigurationProvider` is the seam; the shipped provider returns a local fixture and the shared JSON validator/assembler rejects invalid fields and bounds. Any future Bedrock provider belongs behind a backend-only, explicitly requested proposal endpoint, with a constrained JSON schema, asset allowlist, geometry/resource limits, timeout and deterministic fallback. It must not receive or decide rule stages, restrictions, permissions or private Parchi details. Bedrock region/model setup already documented for explanations would not by itself enable scene proposals; the proposal endpoint, backend IAM scope and model-output validation would need a separately reviewed implementation.

## Asset audit

Run `python scripts/audit_3d_assets.py` to regenerate [`3d-assets/asset-inventory.json`](../../3d-assets/asset-inventory.json). The audit reads source archives in place, records all archive files, enumerates each packaged model format and texture path, parses GLB v2 mesh/accessor/image metadata and OBJ geometry counts, checks source-to-runtime hashes for each reused model, and preserves the original ZIP files.

Kenney's Building Kit 1.0, City Kit Commercial 2.1 and City Kit Roads 2.2 identify themselves as CC0 in their included `License.txt` files. Copies of those three license files are in `web/public/models/kenney/`. The runtime currently reuses 9 exact source GLBs; their original source paths, hashes, accessor dimensions, triangle/vertex estimates, image dependency and app path are recorded in the generated inventory and in the typed registry.

The source library also includes three Blender archives with textures but no in-archive license or attribution file, and a ZIP containing four unrelated case-study PDFs. Blender/Assimp/FBX SDK tooling is unavailable in this workspace. Those Blender models are recorded as unknown-license/uninspected and are not copied to runtime; the PDFs are catalogued but are not 3D assets. Source archives remain untouched.
