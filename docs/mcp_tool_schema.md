# MCP tool schema (outline, not final)

Required deliverable: the tools the agent can call and what they return.

- One tool per category (sales methodology, segmentation and territory, enablement operations).
  Names and parameters to be decided.
- Inputs: question text; optional filters (topic/entity, segment, role).
- Outputs: short results, each with the claim, evidence quote and citation (URL, or internal doc
  title + section), and whether it comes from public or internal sources. A helpful message on
  empty results.
- Retrieval: filter by category (and entity), then vector search using the shared model in `embed/`.
- Access control: **pending the client's answer on how user identity/role is supplied.** Internal
  units must not be returned until that is designed; authorization will happen before retrieval.
