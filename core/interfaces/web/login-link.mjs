// W.Alter web sign-in link (2026-11-11, owner decision): the engine's web GUI prints its sign-in link (the process
// launch token in `?token=`) to stdout, hence to the system journal. The composition turns that printing off
// (`web-runtime.printUrl: false`) and this plugin writes the same link to a root-only file (0600 in a 0700 folder)
// instead. The token lives only as long as the process; it only mints the signed sign-in cookie of a new browser.
// The link is never logged: errors name the file, never its content.
import { mkdirSync, renameSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

export const name = 'walter-web-login';
export const inject = ['webServer'];

export function apply(ctx, config = {}) {
  const file = config.file;
  if (!file) throw new Error('walter-web-login: file is required');
  ctx.inject(['connection'], (c) => {
    const write = () => {
      try {
        const port = c.webServer?.port;
        if (port === undefined) throw new Error('webServer port unknown');
        const url = c.connection.authenticatedUrl(`http://127.0.0.1:${String(port)}`);
        mkdirSync(dirname(file), { recursive: true, mode: 0o700 });
        const tmp = `${file}.tmp`;
        writeFileSync(tmp, `${url}\n`, { mode: 0o600, flag: 'w' });
        renameSync(tmp, file);
        console.log(`walter-web-login: sign-in link written to ${file}`);
      } catch (e) {
        console.error(`walter-web-login: could not write the sign-in link to ${file}: ${e instanceof Error ? e.message : String(e)}`);
      }
    };
    const settled = c.get('loader')?.await();
    if (settled === undefined) write(); else settled.then(write, write);
  });
}
