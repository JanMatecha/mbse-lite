import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";

const toolDirectory = dirname(fileURLToPath(import.meta.url));
const packageMetadata = JSON.parse(
  await readFile(resolve(toolDirectory, "package.json"), "utf8")
);
const versions = packageMetadata.devDependencies;
const outputDirectory = resolve(
  toolDirectory,
  "../../src/mbse_lite/_vendor/viewer"
);
const threeAsset = `three-viewer-${versions.three}.min.js`;
const mermaidAsset = `mermaid-${versions.mermaid}.min.js`;

await mkdir(outputDirectory, { recursive: true });
await build({
  entryPoints: [resolve(toolDirectory, "three-entry.js")],
  outfile: resolve(outputDirectory, threeAsset),
  bundle: true,
  minify: true,
  format: "iife",
  platform: "browser",
  target: "es2020",
  charset: "utf8",
  legalComments: "eof"
});
await copyFile(
  resolve(toolDirectory, "node_modules/mermaid/dist/mermaid.min.js"),
  resolve(outputDirectory, mermaidAsset)
);
await copyFile(
  resolve(toolDirectory, "node_modules/three/LICENSE"),
  resolve(outputDirectory, "three-LICENSE.txt")
);
await copyFile(
  resolve(toolDirectory, "node_modules/mermaid/LICENSE"),
  resolve(outputDirectory, "mermaid-LICENSE.txt")
);

async function sha256(fileName) {
  const content = await readFile(resolve(outputDirectory, fileName));
  return createHash("sha256").update(content).digest("hex");
}

const manifest = {
  schema_version: 1,
  build_tool: `esbuild@${versions.esbuild}`,
  dependencies: {
    three: {
      version: versions.three,
      source: `https://www.npmjs.com/package/three/v/${versions.three}`,
      asset: threeAsset,
      sha256: await sha256(threeAsset),
      license: "MIT",
      license_file: "three-LICENSE.txt"
    },
    mermaid: {
      version: versions.mermaid,
      source: `https://www.npmjs.com/package/mermaid/v/${versions.mermaid}`,
      asset: mermaidAsset,
      sha256: await sha256(mermaidAsset),
      license: "MIT",
      license_file: "mermaid-LICENSE.txt"
    }
  }
};
await writeFile(
  resolve(outputDirectory, "manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8"
);
