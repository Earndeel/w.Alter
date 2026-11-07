# Private Community / Server Update Checks

Use this reference when Monsieur asks for the latest announcements from a Discord, Slack, VIP community, or other authenticated channel.

## Evidence boundary

Separate the result into two states:

- `DIRECT_PRIVATE_CHANNEL`: the requested server/channel was opened in an authenticated session and the messages were read.
- `PUBLIC_FIRST_PARTY_FALLBACK`: the private channel was not reached, but the provider's own public changelog, API updates, model pages, or support pages were checked.
- `SEARCH_LEAD`: a public search result suggests an invite or announcement, but it has not been opened and verified.
- `BLOCKED_AUTH`: the service requires login, OAuth consent, MFA, or an account-specific invitation.

Never present `PUBLIC_FIRST_PARTY_FALLBACK` as if it were a Discord reading. Public announcements may mirror the server, but that is an assumption unless the provider explicitly says so.

## Safe sequence

1. Open the provider's official site and locate its public updates/changelog and the community/support entry point.
2. Inspect whether the community link is public or gated. A button such as `Authorize & Join`, `Connect Discord`, or `Create private support channel` is an external authorization or provisioning action.
3. Do not click an OAuth consent, join, or channel-creation button unless Monsieur explicitly asked to join/authorize it. Do not request or type Discord credentials, passwords, MFA codes, or recovery data.
4. Open the Discord URL read-only if a public invite or existing authenticated browser session is available. Verify whether the resulting page shows a logged-in server/channel list or a login screen.
5. If direct access is blocked, search the provider's official public pages and use the latest first-party update page as a clearly labelled fallback. Include the exact source URL and source date.
6. Report the limitation first, then list the verified public updates. Offer a public invite or an already-authenticated session as the next safe input; never ask for credentials.

## Kie.ai example — session snapshot, revalidate before reuse

During the August 2026 check, Kie.ai's VIP support page exposed a gated Discord path requiring account authorization to create a private VIP support channel. The unauthenticated Discord page showed a login screen, so no private-server content was claimed. The public fallbacks were:

- `https://kie.ai/api-updates` — public API announcements.
- `https://kie.ai/seedance-2-0` — current public Seedance 2.0 page; the banner/model labels may mix `Mini`, `Fast`, and `Seedance 2`, so quote the visible label and selected variant rather than normalizing them silently.
- `https://kie.ai/minimax-h3` — current public MiniMax H3 capabilities and pricing page.
- `https://kie.ai/grok-imagine?model=grok-imagine%2Fupscale` — current public Grok 1080P/upscale entry point.

These URLs and observations are a workflow example, not a durable claim that the server remains gated or that the listed announcements/prices are current. Re-open the first-party page for every new request.

## Output contract

Use wording such as: `Je n'ai pas pu vérifier le canal Discord directement; j'ai vérifié les annonces publiques officielles de [provider].` Then separate:

1. Direct Discord findings, if any.
2. Public first-party findings.
3. Search leads, if any.
4. Exact blocker and the smallest safe next step.

Do not say `le Discord annonce X` when only the provider's public website shows X.
