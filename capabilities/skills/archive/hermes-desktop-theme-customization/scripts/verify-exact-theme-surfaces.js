// Run in Hermes Desktop DevTools or via CDP Runtime.evaluate.
// Verifies rendered surfaces, not stored theme seeds.
(() => {
  const sample = (selector, element) => {
    const node = element ?? document.querySelector(selector)

    if (!node) {
      return { selector, present: false }
    }

    const style = getComputedStyle(node)

    return {
      selector,
      present: true,
      backgroundColor: style.backgroundColor,
      backgroundImage: style.backgroundImage,
      exactBlack: style.backgroundColor === 'rgb(0, 0, 0)'
    }
  }

  const surfaces = {
    body: sample('body', document.body),
    conversation: sample('[data-chat-surface]'),
    userBubble: sample('.composer-human-message'),
    composerPaintLayer: sample("[data-slot='composer-surface'] > div[aria-hidden]")
  }
  const present = Object.values(surfaces).filter(item => item.present)

  return {
    theme: document.documentElement.dataset.hermesTheme ?? null,
    mode: document.documentElement.dataset.hermesMode ?? null,
    backdropPresent: Boolean(document.querySelector('img[src*="filler-bg0"]')),
    surfaces,
    exactBlackPass: present.length > 0 && present.every(item => item.exactBlack),
    patternFreePass: present.every(item => item.backgroundImage === 'none')
  }
})()
