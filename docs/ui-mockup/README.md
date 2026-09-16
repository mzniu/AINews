# AINews Dashboard UI Mockup

Static HTML/CSS preview of the AINews dashboard. No build step required.

## Open locally

```bash
cd docs/ui-mockup && python3 -m http.server 8765
# http://localhost:8765/dashboard-preview.html
```

Open `dashboard-preview.html` in your browser. Use the **切换主题** button in the preview banner to toggle light/dark mode.

## Files

| File | Purpose |
|------|---------|
| `dashboard-preview.html` | Main preview page |
| `mockup.css` | Layout and component styles |
| `tokens.css` | Design tokens (light/dark) |
| `theme.js` | Theme toggle (persists in `localStorage`) |
| `fonts/` | Bundled Newsreader + Roboto fonts |
| `assets/` | Logo and SVG sprites |

## GitHub

Browse or download from the repo: `docs/ui-mockup/dashboard-preview.html`
