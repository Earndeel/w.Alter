# lucide-react Icon Pitfalls for Landing Pages

## Version-Specific Icon Names

Not all icon names exist in all versions of lucide-react. Social media icons are particularly unreliable:

| Icon Name | Status |
|-----------|--------|
| `Instagram` | NOT available in many versions |
| `Twitter` | NOT available in many versions |
| `Facebook` | NOT available in many versions |
| `Github` | Usually available |
| `Globe` | Always available — safe fallback for social |
| `MessageCircle` | Always available — safe fallback |
| `Share2` | Always available |
| `ExternalLink` | Always available |

## Verification Before Import

```bash
# Check if specific icons exist in the installed version
node -e "const l = require('lucide-react'); console.log(Object.keys(l).filter(k => /instagram|twitter|facebook/i.test(k)))"
```

If empty array → icons don't exist. Use alternatives.

## Safe Import Pattern

```tsx
// Instead of importing social icons directly:
import { Globe, MessageCircle, ExternalLink } from 'lucide-react';

// In JSX, use generic icons with aria-label:
<Globe className="w-4 h-4" aria-label="Website" />
<MessageCircle className="w-4 h-4" aria-label="Contact" />
```

## Build Error Symptoms

If you import a non-existent icon, the build will fail with:
```
error: "Instagram" is not exported by "node_modules/lucide-react/dist/esm/icons/index.js"
```

Fix: replace with an available icon from the table above.
