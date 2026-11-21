"""End-to-end check of the Router code on the native route (real calls, synthetic content): structured.decisions on
chain ['liquidai/d1.2-ultra'] with typed kinds, an image, audio, boxes. Prints verdicts only (no key)."""
import asyncio, base64, json, sys
sys.path.insert(0, "/walter/cognition/router/llm"); sys.path.insert(0, "/walter/cognition/router/bench")
import httpx, liquid_common as lc, structured

CHAIN = sys.argv[1:] or ["liquidai/d1.2-ultra"]
PNG3, T3 = lc.squares_png(3)
fr = "data:audio/wav;base64," + base64.b64encode(open(sys.argv[0].replace("liquid_native_e2e.py", "") + "../../../../tmp/none", "rb").read()).decode() if False else None

def key(name): return lc.grants.env_value(name, "router")

async def go(label, body, chain=CHAIN):
    logs = []
    async with httpx.AsyncClient() as client:
        code, out = await structured.decisions(body, chain=chain, key=key, client=client, log=logs.append)
    txt = json.dumps({k: out.get(k) for k in ("answers", "error", "route", "cost_usd", "cost_status", "calls", "attempts")}, ensure_ascii=False, default=str)
    print(label, code, lc.mask(txt)[:700]); print()

async def main():
    msg = "Rappelle-moi d'appeler Paul Martin demain avant 18h pour le devis de 300 euros, mais ne lui envoie rien par mail."
    await go("mixed single call", {"state": {"m": msg}, "questions": {
        "mail": {"type": "noul", "instructions": "Faut-il envoyer un mail ?"},
        "who": {"type": "text", "instructions": "Qui appeler ?"},
        "amount": {"type": "number", "instructions": "Montant ?", "unit": "EUR"},
        "tags": {"type": "choice", "multiple": True, "instructions": "Sujets ?", "criteria": {"appel": "appeler", "mail": "e-mail", "devis": "devis"}},
        "n": {"type": "number", "instructions": "Combien de personnes à appeler ?", "range": [0, 10], "step": 1}}})
    await go("image boxes", {"state": {"m": "image"}, "media": [{"type": "image", "data": PNG3}], "questions": {
        "red": {"type": "boxes", "instructions": "Chaque carré rouge", "max": 6}, "cnt": {"type": "number", "instructions": "Combien de carrés rouges ?", "range": [0, 10], "step": 1}}})
    await go("box with 2 images (refused by name)", {"state": {"m": "image"}, "media": [{"type": "image", "data": PNG3}, {"type": "image", "data": PNG3}], "questions": {
        "red": {"type": "box", "instructions": "le carré rouge"}}})
    import os
    wav = "/tmp/claude-0/-root/4fe4bae5-dcfd-4d8c-85b6-b8c919662803/scratchpad/liquid/fr.wav"
    clip = "data:audio/wav;base64," + base64.b64encode(open(wav, "rb").read()).decode()
    await go("audio", {"state": {"m": "note vocale"}, "media": [{"type": "audio", "data": clip}], "questions": {
        "refund": {"type": "noul", "instructions": "Does the speaker ask for a refund?"}}})
asyncio.run(main())
