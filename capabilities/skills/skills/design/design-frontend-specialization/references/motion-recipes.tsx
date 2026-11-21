# Motion Animation Recipes

Quick copy-paste recipes for the most common animation patterns using Motion (motion.dev).

## 1. Fade In Up (most common)

```tsx
import { motion } from "motion/react"

<motion.div
  initial={{ opacity: 0, y: 24 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.4, ease: [0.25, 0.1, 0.25, 1] }}
>
  {content}
</motion.div>
```

## 2. Fade In on Scroll

```tsx
<motion.div
  initial={{ opacity: 0, y: 40 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true, margin: "-80px" }}
  transition={{ duration: 0.5, ease: "easeOut" }}
>
  {content}
</motion.div>
```

## 3. Stagger Children

```tsx
const container = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.1 },
  },
}

const item = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.3 } },
}

<motion.div variants={container} initial="hidden" animate="visible">
  {items.map((el, i) => (
    <motion.div key={i} variants={item}>{el}</motion.div>
  ))}
</motion.div>
```

## 4. Scale on Hover

```tsx
<motion.div
  whileHover={{ scale: 1.04 }}
  whileTap={{ scale: 0.97 }}
  transition={{ type: "spring", stiffness: 400, damping: 17 }}
>
  <Card />
</motion.div>
```

## 5. AnimatePresence (Fade + Scale Exit)

```tsx
import { AnimatePresence, motion } from "motion/react"

<AnimatePresence mode="wait">
  {isVisible && (
    <motion.div
      key="modal"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
    >
      <Modal />
    </motion.div>
  )}
</AnimatePresence>
```

## 6. Layout Animation (Auto-animate reorder/resize)

```tsx
<motion.div layout transition={{ type: "spring", stiffness: 500, damping: 30 }}>
  {/* Automatically animates position/size changes */}
</motion.div>
```

## 7. Shared Layout (Magic Move)

```tsx
// Selected state in list
{items.map((item) =>
  item.isSelected ? (
    <motion.div key={item.id} layoutId={`item-${item.id}`}>
      <ExpandedCard item={item} />
    </motion.div>
  ) : (
    <motion.div key={item.id} layoutId={`item-${item.id}`}>
      <CompactCard item={item} />
    </motion.div>
  )
)}
```

## 8. Scroll Progress Bar

```tsx
import { motion, useScroll, useSpring } from "motion/react"

function ScrollProgress() {
  const { scrollYProgress } = useScroll()
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30 })

  return (
    <motion.div
      style={{ scaleX, transformOrigin: "left" }}
      className="fixed top-0 left-0 right-0 h-1 bg-blue-500 origin-left z-50"
    />
  )
}
```

## 9. Parallax Section

```tsx
import { motion, useScroll, useTransform } from "motion/react"

function ParallaxBg() {
  const { scrollYProgress } = useScroll()
  const y = useTransform(scrollYProgress, [0, 1], ["0%", "30%"])
  const opacity = useTransform(scrollYProgress, [0, 0.5, 1], [1, 0.8, 0.3])

  return (
    <motion.div
      style={{ y, opacity }}
      className="absolute inset-0 bg-cover bg-center"
      style={{ backgroundImage: `url(${bgImage})` }}
    />
  )
}
```

## 10. Number Counter

```tsx
import { motion, useSpring, useTransform, useInView } from "motion/react"

function AnimatedCounter({ value }: { value: number }) {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true })
  const spring = useSpring(0, { stiffness: 60, damping: 20 })
  const display = useTransform(spring, (v) => Math.round(v))

  useEffect(() => {
    if (isInView) spring.set(value)
  }, [isInView, spring, value])

  return <motion.span ref={ref}>{display}</motion.span>
}
```

## Reduced Motion

Always respect user preferences:

```tsx
import { useReducedMotion } from "motion/react"

const shouldReduce = useReducedMotion()

<motion.div
  animate={shouldReduce ? {} : { opacity: 1, y: 0 }}
  initial={shouldReduce ? {} : { opacity: 0, y: 20 }}
/>
```

## Transition Presets

```tsx
// Gentle (default for UI)
const gentle = { duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }

// Bouncy (for emphasis)
const bouncy = { type: "spring", stiffness: 300, damping: 15 }

// Snappy (for interactions)
const snappy = { type: "spring", stiffness: 500, damping: 30 }

// Smooth (for backgrounds)
const smooth = { duration: 0.6, ease: [0.16, 1, 0.3, 1] }
```
