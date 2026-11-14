# localStorage Injection: Add Custom Theme to Desktop App

Open DevTools in Hermes Desktop (`Cmd+Opt+I` or `View → Toggle Developer Tools`),
paste into Console, then restart app.

```js
localStorage.setItem('hermes-desktop-user-themes-v1', JSON.stringify({
  walter: {
    name: 'walter',
    label: 'W.Alter',
    description: 'Pure black — elegant, no-nonsense',
    colors: {
      background: '#000000',
      foreground: '#e8e0d5',
      card: '#0d0d0d',
      cardForeground: '#e8e0d5',
      muted: '#1a1a1a',
      mutedForeground: '#8a8075',
      popover: '#0f0f0f',
      popoverForeground: '#e8e0d5',
      primary: '#e8e0d5',
      primaryForeground: '#000000',
      secondary: '#1c1c1c',
      secondaryForeground: '#c8bda8',
      accent: '#1a1a15',
      accentForeground: '#d8ccb0',
      border: '#2a2a20',
      input: '#2a2a20',
      ring: '#c8aa6e',
      midground: '#c8aa6e',
      destructive: '#b94a3a',
      destructiveForeground: '#fef2f2',
      sidebarBackground: '#000000',
      sidebarBorder: '#1a1a10',
      userBubble: '#1a1a10',
      userBubbleBorder: '#3a3020'
    }
  }
}))
```

Theme appears in Settings → Appearance, between Midnight and Ember.
Survives app restarts (localStorage persists).
