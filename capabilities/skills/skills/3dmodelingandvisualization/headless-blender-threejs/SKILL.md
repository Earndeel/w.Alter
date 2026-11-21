---
name: headless-blender-threejs
description: Use when generating, revising, or verifying editable Blender models and offline Three.js viewers on Monsieur's Ubuntu ARM VM without a desktop session.
---

## Locate or stage Blender
- Run `uname -m; command -v blender || true; apt-cache policy blender; df -h .`. Check for an existing launcher under `/apps/blender` before creating a project copy. The session verified a project-local `./work/blender` running Blender 4.0.2; it did not install Blender under `/apps`. Use `/apps/blender` for a shared copy if Monsieur authorizes that change. An idle installation takes disk space, not process RAM or CPU; check with `du -sh work/runtime/blender` and `pgrep -ax blender || true`.
- To stage a project-local runtime without installing packages system-wide, run the following from the project root:
  ```sh
  mkdir -p work/runtime/debs/partial work/runtime/blender
  apt-get -y --download-only -o Dir::Cache::archives="$PWD/work/runtime/debs" install --no-install-recommends blender >work/apt.log 2>&1 &&
    find work/runtime/debs -name '*.deb' -exec dpkg-deb -x {} work/runtime/blender \;
  ```
- Create `work/blender` with the wrapper below, then run `chmod +x work/blender; ./work/blender --version`. This sets paths for the extracted runtime on the ARM VM. If the launcher fails, inspect `work/apt.log` and check for missing libraries with `ldd work/runtime/blender/usr/bin/blender | grep 'not found'`; do not silently fall back to installing system packages.
  ```sh
  #!/bin/sh
  base="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/runtime/blender/usr"
  export LD_LIBRARY_PATH="$base/lib/aarch64-linux-gnu:$base/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  export BLENDER_SYSTEM_SCRIPTS="$base/share/blender/scripts"
  export BLENDER_SYSTEM_DATAFILES="$base/share/blender/datafiles"
  exec "$base/bin/blender" "$@"
  ```

## Build, render, and verify
- Keep the `bpy` generator, render scripts, and logs in `work/`; put the editable `.blend`, GLBs, and presentation files in `livraison/`. For image-based models, separate visible shapes from estimated dimensions and proposed internals. Name parts and keep assemblies separate so the exploded view and object-level checks are reproducible.
- Generate with `./work/blender -b --python-exit-code 1 --python work/model.py >work/blender.log 2>&1`. Have the script save the `.blend` and export the GLBs. Read the log and check the expected output files before continuing. Guard version-specific material sockets with `.get()` and an explicit fallback: Blender 4.0.2 rejected `bs.inputs['Iridescence Weight']` with a `KeyError`. Verify the material in the exported viewer as well as in Blender; don't assume Blender's shader will transfer unchanged.
- Render small, low-sample previews before spending VM CPU on final frames. Open the PNGs with the image tool and iterate on geometry, camera, and lighting. Check assembled and exploded views, front/profile fit when relevant, and backlighting for translucent parts. Use distinct preview and final filenames so a stale preview cannot pass as a final render.
- Reopen the saved scene for an independent check: `./work/blender -b livraison/model.blend --python-exit-code 1 --python work/verify_models.py >work/verify-models.log 2>&1`. Substitute the actual filenames. Have the verifier assert expected scenes, part counts or names, and key dimensions; check the exit status and log before packaging.

## Package an offline Three.js viewer
- Keep the editable viewer source separate from the generated HTML. A working dependency pair was `npm install --prefix work/web three@0.180.0 esbuild@0.25.12`. If an offline install returns `ENOTCACHED`, the requested tarball is absent; use a verified cached version or allow a normal fetch if network access is permitted.
- Bundle Three.js and its add-ons with esbuild and embed the bundle and GLB payloads in the HTML. Do not leave CDN imports or runtime fetches for neighboring files if promising a single offline file. Open the delivered HTML itself from disk with network disabled. Check that the models load, orbit and zoom work, exploded and preset views switch correctly, and controls fit a mobile viewport. Capture screenshots for visual inspection. If headless browser execution is blocked by sandbox policy, use the approved permission flow rather than reporting an unrun test as passed.
- Deliver the HTML, `.blend`, GLBs, and verified renders. Use terminal scripts plus rendered images by default for reproducible edits; use GUI control when interactive sculpting or live visual adjustment is actually needed. An MCP that runs the same `bpy` script changes the interface, not Blender's modeling capabilities.
