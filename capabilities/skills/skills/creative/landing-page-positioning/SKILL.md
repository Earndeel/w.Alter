---
name: landing-page-positioning
description: Position landing pages by audience. B2C vs technical separation, copy register rules, plan naming, and sign-in CTA wiring. Use whenever a product has both end-user customers and developer/partner integrators and the root landing must speak to one without losing the other.
version: 1.0.0
author: Hermes Agent (W.Alter)
license: MIT
metadata:
  hermes:
    tags: [landing, copywriting, positioning, b2c, marketing, design]
    related_skills: [claude-design, popular-web-designs, sketch]
---

# Landing Page Positioning

When a product has both end-user customers and developer/partner integrators, the public landing and the integration page must be designed as two separate artifacts with different vocabularies. Collapsing them produces a page that reads like documentation to consumers and like marketing fluff to developers — wrong on both sides.

Load this skill before designing or rewriting the root landing of any product that has more than one audience. Pair with claude-design for the process and popular-web-designs for the visual vocabulary.

## Symptoms that a B2C landing is positioned wrong

If any of these appear above the fold on a consumer landing, restart from the audience question.

- Pipeline or architecture diagrams used as primary hero content
- Tables comparing models, providers, routers, presets
- Code samples or shell commands anywhere on the marketing page
- Jargon: orchestrator, pipeline, provider, webhook, preset, inference, SDK, integration
- Plan names borrowed from B2B SaaS (Starter, Pro, Enterprise) instead of user-shaped names
- Hero copy describing how it works internally rather than what the user gets
- Mock interfaces that show the system, not the delivered result

The single-sentence diagnostic: if a non-technical buyer would have to look up a word in your hero copy, the positioning is off.

## Correct B2C structure

1. Hero. Outcome-led headline in the user's own words. Visual mock of the result a customer receives (a chat thread with a finished video, an inbox notification, a download), not a system diagram.
2. How it works. Three steps maximum, each a verb the user does: Describe, Choose, Receive. Not internal pipeline stages.
3. Before and after, or proof block. Concrete savings: money, time, headcount avoided. Real numbers when available, honest ranges when not. Skip rather than fabricate.
4. Testimonials. Real names, real stars, real outcomes. Omit the section if there is nothing real to put in it.
5. Pricing. Plans named for the user's self-image: Discovery, Creator, Studio. Free tier first when it exists. Price in large numerals, billing cadence in small type.
6. FAQ. Answers the objections a non-technical buyer actually has: do I need to know how to film, what if I don't like the result, is my brand safe. Not API rate limits.
7. Footer. Discreet link to the technical or integration page for partners (for example /connect, /api, /developers).

## Keep the technical page separate

For partners, integrators, and developers who genuinely need the implementation story:

- Distinct URL such as /connect
- Distinct layout signal: denser, monospace accents allowed, code samples welcome
- Architecture diagram lives here, not on the home page
- Linked from the marketing footer, not from the hero

This separation lets the B2C landing breathe without losing the technical audience, who will find /connect via the footer or the docs anyway.

## Sign-in CTA wiring

Buttons on the landing should target the auth initiation route on the API host directly, which then redirects to the identity provider. Avoid linking to a frontend page that hosts another button.

Reasons:

- Removes one click and one full page paint between intent and the provider's consent screen.
- On static hosts that rewrite .html to extensionless URLs (Cloudflare Pages does this with a 308), the bouncing frontend page can drop query string state mid-redirect, breaking flows that depend on state or redirect_uri round-trips.
- One origin point for the funnel is easier to instrument.

Verification before shipping: probe the endpoint with a single GET and confirm it returns a 302 to the provider's consent host. If it returns 200 (rendered an HTML page) or 308 (path rewrite), the wiring is wrong and the auth flow will be flaky.

Use extensionless paths in links (link to /login, not /login.html) when the host is Cloudflare Pages, to avoid the same 308 problem on the page itself.

## Product landing + app contract

When the request says "build the platform" and also asks for a landing page, treat the public landing and the learning/product workspace as two required surfaces, not two names for the same dashboard.

- `/` is the public, outcome-led landing page: hero, method, curriculum proof, mentor/product story, objections, and a clear CTA.
- `/app` is the product workspace: keep the existing learning interactions, progress state, practice flow, and mentor affordances intact.
- Make `/app` directly reloadable on the target static host (for Cloudflare Pages, use the SPA fallback in `public/_redirects`) and verify it with a fresh browser load.
- Wire landing CTAs to the product/auth entrypoint, not to a decorative modal or a dashboard screenshot.
- Do not claim an AI teacher, audio service, or model provider unless a live backend or browser capability is actually wired and tested. A local rule-based demo should be labeled as such.

This contract prevents the common failure mode where a dashboard is shipped as the homepage and called a complete platform.

## Quick decision matrix

| Audience | URL | Hero | Copy register | CTAs |
|---|---|---|---|---|
| Consumers, prosumers, SMB owners | / | Outcome plus emotional mock | Plain, benefit-led, no jargon | Start free, See examples |
| Developers, integrators, SaaS partners | /connect, /api, /developers | Diagram plus code sample OK | Technical, precise | Read the docs, Get an API key |
| Internal or admin | unlisted | Sparse, dashboard-style | Operational | Sign in |

When in doubt, default to B2C voice for the root URL. Technical audiences will find /connect from the footer; consumers bounce instantly from a landing that talks about webhooks.

## Aesthetic notes that travel well

- Noir absolu plus an amber or warm accent, with an editorial serif headline (Instrument Serif) and a neutral sans body (Inter), reads as premium without feeling enterprise.
- A chat-style mock (Telegram, iMessage, WhatsApp) in the hero communicates how the user will actually interact with the product better than any feature grid.
- Accordion FAQ beats a long-form FAQ when the page already has seven or more sections; keeps the scroll honest.

## Pitfalls

- Single landing for two audiences. The compromise satisfies neither. Always two URLs.
- Naming the free tier Starter. Starter signals B2B SaaS funnel. Discovery, Free, or Hobby reads consumer.
- Hero mock that shows the dashboard. Show the result instead, ideally arriving in a context the buyer recognises.
- Adding social proof you don't have. Empty testimonial section beats fabricated quotes.
- Linking the sign-in button to /login.html on Cloudflare Pages. The 308 will eat the redirect chain.
- Believing technical buyers want the same page. They actively prefer /connect; it signals you take them seriously.
