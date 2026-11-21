# GSAP Quick Reference

## Core Methods

```javascript
import { gsap } from "gsap";

gsap.to(target, vars)      // animate TO vars
gsap.from(target, vars)    // animate FROM vars
gsap.fromTo(target, fromVars, toVars)  // explicit start/end
gsap.set(target, vars)     // instant apply
gsap.killTweensOf(target)  // kill active tweens
gsap.getProperty(target, "x")  // get current value
```

## Timeline

```javascript
const tl = gsap.timeline({
  defaults: { duration: 0.5, ease: "power2.out" },
  paused: true,      // create paused
  repeat: -1,        // infinite
  yoyo: true,        // alternate direction
  onComplete: () => {}
});

tl.to(".a", { x: 100 })
  .to(".b", { y: 50 }, "+=0.2")      // 0.2s after prev end
  .to(".c", { opacity: 0 }, "-=0.1")  // 0.1s before prev end
  .to(".d", { scale: 2 }, "<")        // same start as prev
  .to(".e", { x: 50 }, 1)             // absolute time 1s
  .addLabel("mid", "+=0.5")           // add label
  .to(".f", { y: 20 }, "mid");        // at label

// Playback
tl.play()
tl.pause()
tl.reverse()
tl.restart()
tl.seek(2)           // jump to 2 seconds
tl.progress(0.5)     // jump to 50%
tl.timeScale(2)      // double speed
tl.kill()            // destroy
```

## Easing

```javascript
// Power (default: power1.out)
"power1.out" | "power2.inOut" | "power3.in" | "power4.out"

// Special
"back.out(1.7)"      // overshoot
"elastic.out(1, 0.3)" // bounce
"bounce.out"
"circ.inOut"
"expo.inOut"
"none"               // linear

// CustomEase (plugin)
"custom"             // define with CustomEase.create()
```

## Stagger

```javascript
// Number: delay between each
gsap.to(".box", { x: 100, stagger: 0.1 });

// Object: fine control
gsap.to(".box", {
  x: 100,
  stagger: {
    amount: 0.5,     // total time for all
    from: "center",  // "start" | "end" | "center" | "edges" | "random"
    grid: [3, 4],    // for 2D stagger
    axis: "y"        // stagger axis
  }
});
```

## ScrollTrigger

```javascript
import { ScrollTrigger } from "gsap/ScrollTrigger";
gsap.registerPlugin(ScrollTrigger);

// Basic trigger
gsap.to(".box", {
  x: 500,
  scrollTrigger: {
    trigger: ".box",
    start: "top center",     // triggerPos viewportPos
    end: "bottom center",
    toggleActions: "play reverse play reverse"
  }
});

// Pinning
gsap.to(".content", {
  y: -200,
  scrollTrigger: {
    trigger: ".section",
    start: "top top",
    end: "+=500",
    pin: true,
    scrub: true
  }
});

// Standalone (no tween)
ScrollTrigger.create({
  trigger: "#section",
  start: "top top",
  onEnter: (self) => console.log(self.progress),
  onUpdate: (self) => console.log(self.direction)
});

// Batch (IntersectionObserver-like)
ScrollTrigger.batch(".card", {
  interval: 0.1,
  onEnter: (elements) => gsap.to(elements, { opacity: 1, stagger: 0.1 })
});

// Refresh after layout change
ScrollTrigger.refresh();
```

### ScrollTrigger Config Options

| Property | Description |
|----------|-------------|
| `trigger` | Element that drives the trigger |
| `start` | When active (e.g. `"top center"`, `"top 80%"`) |
| `end` | When inactive (e.g. `"bottom top"`, `"+=300"`) |
| `scrub` | Link to scroll (boolean or lag seconds) |
| `pin` | Pin element while active |
| `pinSpacing` | Add spacer (default true) |
| `toggleActions` | `"onEnter onLeave onEnterBack onLeaveBack"` |
| `markers` | Dev markers (remove in prod) |
| `once` | Kill after first end |
| `horizontal` | Horizontal scroll mode |
| `snap` | Snap to progress values |

## React (@gsap/react)

```tsx
import { useGSAP } from "@gsap/react";
import { useRef } from "react";

function Component() {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    gsap.to(".box", { x: 100 });
    // cleanup auto-handled
  }, { scope: ref, dependencies: [someState] });

  return <div ref={ref}>...</div>;
}
```

## Plugins

```javascript
// Register (once per app)
gsap.registerPlugin(ScrollTrigger, Flip, Draggable, SplitText);

// Flip
const state = Flip.getState(".items");
// ...change DOM...
Flip.from(state, { duration: 0.5, ease: "power2.inOut" });

// SplitText
const split = new SplitText(".text", { type: "words,chars" });
gsap.from(split.chars, { opacity: 0, y: 20, stagger: 0.02 });

// Draggable
Draggable.create(".drag", { type: "x,y", bounds: ".container" });
```

## Transform Aliases (Prefer over CSS transform)

| GSAP | CSS Equivalent |
|------|----------------|
| `x`, `y`, `z` | translateX/Y/Z (px default) |
| `xPercent`, `yPercent` | translateX/Y (%) |
| `scale`, `scaleX`, `scaleY` | scale |
| `rotation` | rotate (deg) |
| `rotationX`, `rotationY` | 3D rotate |
| `skewX`, `skewY` | skew |
| `transformOrigin` | transform-origin |
| `svgOrigin` | SVG global origin |

## Common Vars

```javascript
{
  duration: 0.5,           // seconds
  delay: 0.2,              // seconds before start
  ease: "power2.out",
  stagger: 0.1,
  repeat: -1,              // infinite
  yoyo: true,
  overwrite: false,        // true | "auto" | false
  immediateRender: true,   // apply start state immediately
  onComplete: () => {},
  onStart: () => {},
  onUpdate: () => {},
  autoAlpha: 0,            // opacity + visibility
  clearProps: "all"        // remove inline styles on complete
}
```

## Responsive / Accessibility

```javascript
// matchMedia for responsive animations
gsap.matchMedia().add("(min-width: 800px)", () => {
  gsap.to(".box", { x: 100 });
  return () => { /* cleanup */ };
});

// prefers-reduced-motion
gsap.matchMedia().add("(prefers-reduced-motion: no-preference)", () => {
  gsap.to(".box", { x: 100 });
});
```

## Targets

```javascript
gsap.to(".box", { x: 100 });          // selector
gsap.to(el, { x: 100 });               // element
gsap.to([el1, el2], { x: 100 });       // array
gsap.to(document.querySelectorAll(".box"), { x: 100 }); // NodeList
```
