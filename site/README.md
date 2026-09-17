# Raspberry Pi ST7789 Dashboard landing page

Static, bilingual landing page prepared for GitHub Pages and Google indexing.

## Publishing

The repository includes `.github/workflows/pages.yml`, which publishes `site/` whenever the landing page changes on `main`.

Before deployment, the workflow checks:

- `node scripts/validate_site.mjs`: assets (including cache-versioned URLs), metadata, links, translations and saved language preferences;
- `python scripts/validate_site_images.py` (Pillow required): decodable/nonblank images, EXIF-oriented HTML dimensions, original hardware photos and the exact maintainer-confirmed PIX QR;
- `node scripts/validate_site_browser.mjs http://127.0.0.1:8092/` (Playwright/Chromium required): all five images keep their natural proportions at 1440, 980, 390 and 320 pixels, in both languages, without horizontal overflow or browser errors.

For browser verification, serve `site/` locally on port 8092. An existing Playwright installation can be selected with `ST7789_PLAYWRIGHT_PATH` (absolute path to its `index.mjs`); `ST7789_BROWSER_CHANNEL=chrome` uses an installed Chrome in an isolated headless profile. `ST7789_SCREENSHOTS` selects an optional output directory. The workflow installs its own isolated Chromium and does not use personal browser sessions.

Live URL, verified with HTTP 200 on 16/09/2026:

`https://abraaobat.github.io/raspberrypi-st7789-dashboard/`

If the first workflow run requests setup, open **Settings → Pages** in the repository and choose **GitHub Actions** under **Build and deployment**.

## Search indexing

The page includes semantic headings, crawlable text, a canonical URL, descriptions, Open Graph metadata, `SoftwareApplication` JSON-LD, `robots.txt` and `sitemap.xml`.

Search Console registration and sitemap submission remain pending because the available browser requires a Google login. To finish:

1. Sign in to [Google Search Console](https://search.google.com/search-console).
2. Add a **URL-prefix** property with the exact live URL above.
3. Verify ownership with the HTML meta tag. The page currently reuses the maintainer's public verification tag from the ESP32 AdBlocker page; replace it if Google issues a different tag for this property.
4. Open **Sitemaps** and submit:

`https://abraaobat.github.io/raspberrypi-st7789-dashboard/sitemap.xml`

Submission is not a guarantee of immediate indexing. See Google's [property setup](https://support.google.com/webmasters/answer/34592?hl=pt-BR), [ownership verification](https://support.google.com/webmasters/answer/9008080?hl=pt-BR) and [sitemap guidance](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap).

## PIX support

The optional support section uses the same public PIX key and validated QR code already published by the maintainer on the ESP32 AdBlock Gateway page. The maintainer explicitly confirmed this destination before publication. It does not imply a purchase, subscription or exclusive software license.

## Accuracy rules

- Hardware photos must remain byte-for-byte copies of `docs/images/weather.jpg` and `docs/images/sysops.jpg`. A previous resizing conversion erased their pixels; it was replaced with the originals on 16/09/2026.
- Keep responsive image heights automatic. JPEG orientation is EXIF-based (portrait 3024×4032); the web-panel screenshot is landscape and the PIX QR is square. Do not stretch or crop these assets.
- Do not advertise experimental SSD1306 or ILI9341 profiles as physical drivers.
- Keep the local web panel described as LAN/tailnet software, not an Internet-facing service.
- Generic HTTP/JSON sources still do not accept arbitrary auth headers. Only the closed Pi-hole 6/Home Assistant connectors use the v0.4.0 vault; its private file is not disk encryption.
- Keep the v0.3.0 physical-validation badge separate from newer software additions. The active v0.6.0 installation and health checks on the Raspberry Pi were confirmed on 17/09/2026, not the visual validation of newer pages or real connectors. v0.7.0 adds optional local Docker monitoring via an already authorized Unix socket, with separate deployment/real Engine/TFT validation. Fake-service browser tests do not establish real Docker, Pi-hole/Home Assistant, Node-RED or TFT validation. Manual tests are deferred to the maintainer's final checklist. Do not install Docker or grant socket privileges automatically. Preserve all photos and the confirmed Pix destination.
- Update the displayed version and physical-validation statements together with `project-status.json`.
