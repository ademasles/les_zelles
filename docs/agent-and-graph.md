# Knowledge graph and agent harness

The spec sheet answers "what does this CCTP require". The graph and the tools answer the questions an estimator, or an agent working for one, asks next: *where does this apply, which standard governs it, does anything contradict it, can my product meet it, what should I ask the architect*.

## Knowledge graph

`graph/knowledge.py` builds a typed property graph for each document.

```
Document ─CONTAINS→ Lot ─CONTAINS→ Section ─CONTAINS→ Passage ─STATES→ Requirement
                                       │                 │                │
                                       │                 ├─CITES→ Standard ─GOVERNS→ Topic
                                       │                 ├─REQUIRES→ Certification
                                       ├─USES→ Material  └─REFERS_TO→ Section ("voir article 3.2")
                                       └──────────────────────── Requirement ─APPLIES_TO→ Section
                                                                 Requirement ─ABOUT→ Topic
                                                                 Requirement ─CONFLICTS_WITH→ Requirement
```

- **Standards** are normalised (`NF EN 14351-1`, `DTU 36.5`, `EN 12207`...) and linked to the topics they govern through a small ontology in `graph/ontology.py`, so a question about air tightness reaches EN 12207 even when the passage never says "air".
- **Cross-references** such as "conforme à l'article 3.2" become `REFERS_TO` edges to the target section.
- **Conflicts.** For single-valued fields (Uw, Ug, AEV, frame material, acoustic class...), two different values for the same scope create a `CONFLICTS_WITH` edge. These are exactly the points that cause disputes after signing, so they are surfaced in the UI and turned into clarification questions.

Exports: `GET /api/v1/documents/{id}/graph?fmt=json` (node-link, for D3 or networkx) and `?fmt=cypher` (paste into Neo4j to query several tenders together).

## Decision support

- `insights.compare_product`: compares a product's declared performances (Uw, Ug, Sw, TLw, AEV, Ra,tr, RC class, material, colours) to each requirement. Numeric checks respect the comparator and the direction (lower Uw is better, higher Sw is better); AEV classes are compared per part, and a difference in water test method is flagged for review rather than failed.
- `insights.clarification_questions`: drafts, in French, the questions for the project owner: critical fields that are missing, conflicting values and values that failed validation.

## Tool registry

`agent/tools.py` defines each capability once, as a `Tool` with a Pydantic input model, a description and an async function. The same registry is exposed four ways:

| Consumer | How |
|---|---|
| Built-in agent | `zelles agent "question" --doc <id> --trace`, `POST /api/v1/agent` |
| HTTP | `GET /api/v1/tools` (JSON schemas), `POST /api/v1/tools/{name}` |
| MCP | `zelles mcp` (stdio) |
| Native function calling | `registry.openai_tools()`, `registry.anthropic_tools()` |

Tools: `list_documents`, `outline`, `search_passages`, `read_passage`, `get_requirements`, `graph_find`, `graph_neighbors`, `find_conflicts`, `check_product`, `clarification_questions`.

Tools only read analysed documents; they never modify them. Inputs are validated before the function runs, and errors are returned to the model as observations so it can correct itself.

## Agent loop

`agent/loop.py` is a small ReAct-style loop. At each step the model returns one JSON action (`thought`, `action`, `arguments`, or `answer`), validated with Pydantic. This JSON protocol works with any model that can produce JSON, including 7B to 14B local models that do not support native tool calling reliably. The loop stops on an answer, after `max_steps` (8 by default), or on an error, and returns the full trace with token usage.

## MCP server

Install the extra and point your MCP client at the CLI:

```bash
uv sync --extra mcp
```

```json
{
  "mcpServers": {
    "les_zelles": {
      "command": "uv",
      "args": ["--directory", "/path/to/les_zelles", "run", "zelles", "mcp"],
      "env": { "ZELLES_DATA_DIR": "/path/to/les_zelles/data" }
    }
  }
}
```

The server adds `analyze_file(path)` to the registry tools, so a client can analyse a local CCTP and then explore it.
