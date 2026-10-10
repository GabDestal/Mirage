# Mirage brandmark

Use the horizon mark alone, without an illustrated wordmark or adjacent sidebar wordmark. Keep meaningful product names in page titles and UI copy.

- [Scalable transparent SVG](../web/public/brand/mirage-mark.svg): four clean paths traced from the approved original, for login, sidebar, chat and future repo surfaces.
- [Approved raster master](../web/public/brand/mirage-approved-master.png): the unchanged white-background artwork approved on 2026-10-10. This is the geometry authority; keep it for future reuse.
- [Browser favicon](../web/public/favicon.svg) and [180px touch icon](../web/public/apple-touch-icon.png): the same paths on a neutral light square for contrast in browser and home-screen chrome.

Preserve the organic asymmetric navy M peaks, terracotta partial sun and two cobalt flowing ripples. Do not recolor, stretch, filter or change the silhouette. The supplied transparent extraction had stray blue/alpha pixels between the ripples, so it is not used. The clean SVG preserves the approved contours with flat fills; the raster master retains the original texture.

Reference fills are navy `#102744`, terracotta `#d86c45` and cobalt `#1477ff`. Keep these independent of UI status colors. Use explicit image dimensions, retain the aspect ratio, and use `alt="Mirage"` when the mark identifies the product; use an empty alt when adjacent text already names Mirage.

On dark surfaces place the original artwork on a small neutral light backing rather than changing its colors. Login and sidebar retain their existing light surfaces; chat adds a backing only in dark mode. Assets are served from `web/public`; no runtime asset depends on a generated-image folder.
