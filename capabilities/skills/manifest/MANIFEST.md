# W.Alter Skills

**Role.** A library of tested procedures and of workflows (which chain several skills), shared by every agent and
independent of any runtime. A curator maintains it continuously: names, descriptions, domains, merges, archiving and
the index.

**Use**
1. Find the domain (the session's domain map, or `skills_index()`), then `skills_index(domain)`: what each entry is
   for, workflows first.
2. Unknown domain: `skills_search(query)` by intent.
3. `skill_read(name)`, then only the useful references. A workflow points to its component skills.
4. After a task that will recur: `skill_propose`; a wrong or outdated skill: `skill_patch`.

Dormant skills stay findable (marked "reserve") and return to service when read. Live contents:
`module_index("skills")`.
