# Mirage brandmark

Use the horizon mark alone, without an illustrated wordmark or adjacent sidebar wordmark. Keep meaningful product names in page titles and UI copy.

- [Scalable transparent SVG](../web/public/brand/mirage-mark.svg): four clean paths traced from the approved original, for login, sidebar and other brand surfaces.
- [Approved raster master](../web/public/brand/mirage-approved-master.png): the unchanged white-background artwork approved on 2026-10-10. This is the geometry authority; keep it for future reuse.
- [Browser favicon](../web/public/favicon.svg) and [180px touch icon](../web/public/apple-touch-icon.png): the same paths on a neutral light square for contrast in browser and home-screen chrome.

Preserve the organic asymmetric navy M peaks, terracotta partial sun and two cobalt flowing ripples. Do not recolor, stretch, filter or change the silhouette. The supplied transparent extraction had stray blue/alpha pixels between the ripples, so it is not used. The clean SVG preserves the approved contours with flat fills; the raster master retains the original texture.

Reference fills are navy `#102744`, terracotta `#d86c45` and cobalt `#1477ff`. Keep these independent of UI status colors. Use explicit image dimensions, retain the aspect ratio, and use `alt="Mirage"` when the mark identifies the product; use an empty alt when adjacent text already names Mirage.

On dark surfaces place the original artwork on a small neutral light backing rather than changing its colors. Login and sidebar retain their existing light surfaces. Assets are served from `web/public`; no runtime asset depends on a generated-image folder.

UI review captures: [desktop](brand-qa/desktop.webp) and [phone](brand-qa/mobile.webp). Each shows login, chat home/sidebar and a chat reply, with light on the left and dark on the right. Login and sidebar intentionally keep their existing light surfaces in both themes.

## Miragio, the chat assistant

Miragio is the approved rounded square head-and-upper-chest portrait, separate from the horizon brandmark. The [unchanged approved raster](../web/public/brand/miragio-approved-master.png) is its visual authority. [Miragio](../web/src/components/miragio.tsx) traces that navy asymmetric twin crest, ivory face, two dark eyes with catchlights, terracotta sunset disk and two cobalt reflection ribbons into a layered, shaded SVG. The pale tile fills the square crop; retain it in both themes. Do not add legs, clothing, props or recolor the artwork.

Use Miragio at 80px on the chat welcome (64px on phones), and static at 32px in assistant replies (28px on phones). Keep the horizon brandmark on login, sidebar, favicon and other brand surfaces. The welcome alone tracks a gentle gaze, blinks and moves its reflections; composer focus looks down and draft length moves the reading gaze. Every instance has unique SVG definition IDs. Reduced motion is fully still, including live preference changes; hidden documents pause motion and timers. Static replies mount no animation listeners or timers.

[QA evidence and limits](miragio-qa/README.md) includes the approved-source comparison, desktop/phone captures under both OS themes, reduced-motion captures and animation video. The chat intentionally retains its incumbent light surface under dark OS appearance.
