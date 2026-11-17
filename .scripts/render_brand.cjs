#!/usr/bin/env node
/**
 * Render SVG sources into the PNG files Home Assistant expects in an integration's brand/ folder.
 *
 *   node .scripts/render_brand.cjs <folder with svgs> <brand folder>
 *
 * icon.svg, logo.svg and their dark_ variants each become NAME.png and NAME@2x.png. The shorter
 * side is 256 pixels (512 for @2x), whatever the proportions of the viewBox, which is what the
 * brand rules and .scripts/integration_checks.py ask for. Needs Node and Playwright with Chromium.
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const SIDES = [["", 256], ["@2x", 512]];

function viewBox(svg, file) {
  const match = svg.match(/viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)\s*"/);
  if (!match) throw new Error(`${file} needs a viewBox`);
  return [Number(match[1]), Number(match[2])];
}

async function main([source, target]) {
  if (!source || !target) throw new Error("usage: render_brand.cjs <svg folder> <brand folder>");
  fs.mkdirSync(target, { recursive: true });
  const browser = await chromium.launch();
  try {
    for (const file of fs.readdirSync(source).filter((name) => name.endsWith(".svg")).sort()) {
      const svg = fs.readFileSync(path.join(source, file), "utf8");
      const [boxWidth, boxHeight] = viewBox(svg, file);
      for (const [suffix, shorterSide] of SIDES) {
        const factor = shorterSide / Math.min(boxWidth, boxHeight);
        const width = Math.round(boxWidth * factor);
        const height = Math.round(boxHeight * factor);
        const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
        await page.setContent(
          `<style>html,body{margin:0;background:transparent}svg{display:block;width:${width}px;height:${height}px}</style>${svg}`
        );
        const out = path.join(target, `${path.basename(file, ".svg")}${suffix}.png`);
        await page.screenshot({ path: out, omitBackground: true });
        await page.close();
        console.log(`${out} ${width}x${height}`);
      }
    }
  } finally {
    await browser.close();
  }
}

main(process.argv.slice(2)).catch((error) => {
  console.error(error.message);
  process.exit(1);
});
