# 21st.dev Component Sources

21st.dev is a community marketplace for React UI components. All components are:
- React + TypeScript
- Tailwind CSS
- Copy-paste ready
- Open source (community-published)

## URL Structure

| Page | URL |
|------|-----|
| Components home | `https://21st.dev/community/components` |
| Popular | `https://21st.dev/community/components/popular` |
| Newest | `https://21st.dev/community/components/newest` |
| Featured | `https://21st.dev/community/components/featured` |
| Themes | `https://21st.dev/community/themes` |
| Agents | `https://21st.dev/community/agents` |

## Common Component Categories

When searching 21st.dev, use these terms:

| Category | 21st Search Term | Common Components |
|----------|-----------------|-------------------|
| Layout | `layout`, `shell` | Sidebar layout, dashboard shell, page wrapper |
| Navigation | `navbar`, `header`, `sidebar`, `nav` | Top nav, sidebar nav, mobile hamburger |
| Hero | `hero`, `hero section` | Hero with CTA, hero with image, hero with video |
| Cards | `card`, `feature card`, `stat card` | Feature card, pricing card, profile card |
| Forms | `input`, `form`, `sign-in`, `sign-up` | Login form, contact form, search input |
| Buttons | `button`, `cta`, `icon button` | Primary, secondary, ghost, loading button |
| Modals | `modal`, `dialog`, `drawer` | Alert dialog, slide-out, bottom sheet |
| Tables | `table`, `data table` | Sortable table, paginated table |
| Footer | `footer` | Multi-column footer, simple footer |
| Pricing | `pricing`, `pricing table` | Pricing card, pricing comparison |
| Testimonials | `testimonial`, `review` | Testimonial card, carousel |
| Charts | `chart`, `graph` | Bar chart, line chart, stat display |
| FAQ | `faq`, `accordion` | Accordion FAQ, expandable sections |
| Banners | `banner`, `announcement`, `notification` | Top banner, toast notification |

## How to Use 21st.dev Components

1. **Browse** the category page or search
2. **Preview** the component (hover for interactions)
3. **Click** to open the component detail page
4. **Copy** the code (the component page shows the full source)
5. **Paste** into your project under `src/components/`
6. **Adapt** colors/spacing to your Tailwind theme

## Publisher Profiles

Components are published by community members. Notable publishers:
- `tom_ui` — QR codes, tilt cards, visual components
- Search for publishers by clicking their name on any component

## Integration with Motion

21st.dev components are static — they don't include animations. Wrap them in Motion components (see `references/motion-recipes.tsx`).

```tsx
import { motion } from "motion/react"
import { HeroSection } from "@/components/hero-section" // from 21st.dev

// Animate the 21st component on scroll
<motion.div
  initial={{ opacity: 0, y: 20 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true }}
>
  <HeroSection />
</motion.div>
```

## Limitations

- **No public API** — the site uses client-side rendering with tRPC. You must browse it, not curl it.
- **No npm packages** — components are copy-paste, not installable.
- **Quality varies** — prefer components with higher engagement (views, likes).
- **Tailwind-only** — components expect Tailwind to be configured in the project.
