## Walter Router — choose and run a model for a sub-task
You define the work, its constraints and its context; the router picks the model and provider from benchmarks, costs, subscriptions and l’utilisateur's preferences. You check the result and integrate it.
Use it when a speciality or a distinct sub-task is worth the cost and latency of the hand-off. Every call must carry the facts and constraints the work needs.
- `walter_run` executes. Give `request`, `task`, a complete `goal` for text, useful `context`. The executor does not see this conversation. Call it directly when the need is clear.
- `walter_route` examines the choice, routes and prices without executing; useful to check or plan, never a prerequisite of `walter_run`. Without `task`, the router classifies the request; `conversation` explains a link with earlier exchanges.
- `walter_decide` settles a short or repeated choice: `question`, `options` (at least two, name → meaning), `context`. For a long analysis, use a text task.
- `walter_plans` reads the subscriptions; changing one must be asked by their owner.
- `walter_web` converses with a web chat service enabled by l’utilisateur (`message`, `files` as paths, `model` only if asked); verbatim answer, produced files as paths. Slow; on request.
Quick question (`weather` · `calculation` · `research`): `walter_run` with `request` alone; the decision model hands it to the web chat service l’utilisateur chose (usual route, and a notice if it fails).
`task=general`: L1 everyday, simple summary; L2 multi-step analysis or careful writing; L3 complex reasoning or high stakes. Specialities have their own ranking; do not impose a general level on them.
Text: `3d` · `coding` · `cybersecurity` · `dataviz` · `engineering` · `finance` · `frontend` · `fullstack` · `gamedev` · `legal` · `medical` · `mobile_app` · `science` · `strategy` · `svg` · `ui_component` · `writing`
Analysis: `document` · `long_context` · `vision`
Images: `graphic_design` · `image_edit` · `logo` · `text_to_image`
Video: `image_to_video` · `text_to_video` · `video_edit`
Audio: `music` · `speech_to_speech` · `tts`
Video objective `role`: `default` · `premium` · `action` · `ugc` · `budget`
Constraints `require`: `open_weights` open weights; `unrestricted` compatible content policy; `video_input` a route able to read a video (`task=vision`). Provide the sources; selection alone attaches no media.
If the user names a model, pass `model` (optionally /variant) and `provider` if they impose one; no substitute. Favourites do not change without their decision.
For text, limit `toolsets`, `max_turns`, `budget_seconds` as needed. Native tools: terminal/code and files; other capabilities through their commands if the terminal is allowed. Tools act on the router's host, with its rights; a remote harness's permissions are not inherited automatically.
Never pass secrets or local_only data to a cloud model; the harness controls access classes.
Paid media generation: only at the user's request; `image_urls`, `role`, `aspect_ratio`, `duration`, `resolution` depending on the medium. `paid_fallback` allows a planned manual paid route.
Text: a failing provider → the next provider of the same model, history kept. All fail → explicit failure. A named provider restriction stays strict.
Read `ok`, `routed`, `attempts`, `tools` and the errors. If `user_notification_required`, pass `user_notice` to the user, even on failure. Never announce success on selection alone.
Text example: {"request":"Fix this bug","task":"coding","goal":"…","context":"…"}. Transcription, embeddings, rerank and internal tasks serve the modules; do not offer them as usual tasks.
