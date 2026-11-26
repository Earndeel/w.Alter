# W.Alter Skills — detailed guide

## Purpose
Keep W.Alter's procedures and workflows independently of the agents that use them. Let the model find the right
capability, load only the procedure it needs and carry it out with its usual means and permissions.

Success is a task done correctly with a controlled context. The number of skills, archivings or curator passes is
not a measure of success.

## Progressive discovery
1. **Session map**: the purpose of the library, the navigation tools and the compact list of domains. No skill body
   and no per-message candidate list in `on_demand` mode.
2. **Index on demand**: choose a domain to see the names, kinds, uses and components of workflows. Pages hold at most
   20 entries; `next_offset` gives the rest. Workflows come before individual procedures. The index holds active
   entries only.
3. **Search by intent**: if the domain is unknown, describe the need in French or English; the local engine finds
   targeted candidates.
4. **Reserve**: dormant skills stay findable (marked "reserve" in results and at the end of index pages); reading one
   puts it back into service automatically. A merged name points to the skill that contains it; a retired skill can
   be read only as history.
5. **Read and execute**: open the chosen `SKILL.md`, then only the references or scripts needed. A workflow
   orchestrates other skills; consult their procedures for the useful steps.

The model chooses the procedure to read. The curator maintains the library in the background; it does not decide on
each user request. After an error, the policy may still offer at most two cards describing the symptom.

## Components and responsibilities
| Component | Responsibility |
|---|---|
| `store.py`; `skills/`, `archive/`, `drafts/` | Content versioned in Git; published procedures, archives and proposals |
| `registry.py`; schema `skills.*` | Cards, catalogue, labels, ranking models, state and traces |
| `domains.py` | Index publication from active metadata; overview and per-domain navigation |
| `cards.py` | Discovery cards; full procedures are never loaded into the prompt |
| `ranker.py`, `retrieval.py` | Local lexical and semantic search, ranking, skill reading |
| `policy.py` | One exposure policy, independent of runtimes |
| `door.py` | Proposals; a proposal must not overwrite a local change |
| `curation/` | Maintenance of names, descriptions, domains, links and workflows; index publication after active operations |
| `learning.py`, `evaluate.py` | Labels, training and evaluation; they do not replace a check that the task succeeded |
| `jobs.py`, `consumer.py` | Nightly pass, reactions to bus events and reconciliation; index refresh |
| `api.py`, `client.py` | Common HTTP interface (:8891) and light client; the MCP adapter carries the same operations |
| `postes.py` | Access to AI postes through Walter Router for maintenance, off each message's path |

## Index and freshness
Git content is authoritative. The index is a rebuildable projection published in `.cache/library-index.json` and in
the registry's `domain_map` state. Each entry gives `name`, `kind`, `purpose`, `requires`; the overview gives the
domains and the numbers of skills and workflows. The curator republishes the index after its active operations; change
events and reconciliation republish it too; the nightly pass rebuilds it at the end of the chain. A publication
replaces the file atomically. A wrong description is corrected through the proposal door, not by editing the
projection.

## Interfaces
| Need | MCP | HTTP / CLI |
|---|---|---|
| Understand the module | `module_guide("skills")`, `skills_manifest()` | `GET /v1/manifest`; `walter-skills manifest` |
| Browse the index | `skills_index(domain, offset, limit)` | `GET /v1/index`; `walter-skills index [--domain …]` |
| Search by intent | `skills_search(query, context)` | `POST /v1/search`; `walter-skills search` |
| Load a procedure | `skill_read(name, file_path)` | `GET /v1/skill/{name}`; `walter-skills read` |
| Propose / patch | `skill_propose`, `skill_patch` | proposal door (`door.py`) |

`contracts/skills.json` describes the technical contract, dependencies, resources and recovery; `README.md` the
operations. This guide explains the structure; it does not reproduce the live index.

## Limits and operations
- `policy.discovery = "on_demand"` avoids per-message candidate lists; `shortlist` keeps the previous behaviour for
  comparison or rollback.
- Adapters must expose the navigation tools and carry the session map. An already loaded tool schema may need a
  client reconnection.
- If the service is unavailable, the client can read the local manifest; search and reading have a Git fallback.
  An unavailable index is reported explicitly.
- Archivings, rewrites and the relevance of procedures need quality validations; publishing an index does not prove
  them.
