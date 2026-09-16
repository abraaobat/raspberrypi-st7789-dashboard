# Raspberry Pi ST7789 Dashboard landing page

Static, bilingual landing page prepared for GitHub Pages and Google indexing.

## Publishing

The repository includes `.github/workflows/pages.yml`, which publishes `site/` whenever the landing page changes on `main`.

Expected URL:

`https://abraaobat.github.io/raspberrypi-st7789-dashboard/`

If the first workflow run requests setup, open **Settings → Pages** in the repository and choose **GitHub Actions** under **Build and deployment**.

## Search indexing

The page includes semantic headings, crawlable text, a canonical URL, descriptions, Open Graph metadata, `SoftwareApplication` JSON-LD, `robots.txt` and `sitemap.xml`.

After the site is live, add its URL to Google Search Console and submit:

`https://abraaobat.github.io/raspberrypi-st7789-dashboard/sitemap.xml`

## PIX support

The optional support section uses the same public PIX key and validated QR code already published by the maintainer on the ESP32 AdBlock Gateway page. It does not imply a purchase, subscription or exclusive software license.

## Accuracy rules

- Do not advertise experimental SSD1306 or ILI9341 profiles as physical drivers.
- Keep the local web panel described as LAN/tailnet software, not an Internet-facing service.
- Do not claim that custom HTTP/JSON sources support authentication tokens until the local secrets vault exists.
- Update the displayed version and physical-validation statements together with `project-status.json`.
