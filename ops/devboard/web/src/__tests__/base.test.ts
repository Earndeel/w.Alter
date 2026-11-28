import { readFileSync } from "node:fs";
import { api } from "../api";

// Walter Web serves the board under a sub-path (/devboard/): every request must stay relative to the page.
test("les appels de l'API sont relatifs à la page (servie aussi sous /devboard/)", async () => {
  const urls: string[] = [];
  globalThis.fetch = (async (u: string) => { urls.push(String(u)); return new Response("[]"); }) as typeof fetch;
  await api.summary(); await api.cards("status", "x"); await api.doc("/walter/docs/VISION.md");
  expect(urls).toEqual(["api/summary", "api/cards?group=status&q=x", "api/docs/walter/docs/VISION.md"]);
});

test("la page charge ses fichiers en relatif", () => {
  expect(readFileSync("vite.config.ts", "utf8")).toMatch(/base:\s*"\.\/"/);
});
