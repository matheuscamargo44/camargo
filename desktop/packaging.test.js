import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * v0.8.0 shipped broken because backend-manager.js was require()d by
 * main.js but missing from electron-builder's `files` allowlist: the app
 * installed fine and then crashed on launch with "Cannot find module".
 * Nothing caught it because every test runs from source, where the file is
 * obviously present.
 *
 * This walks main.js's own local requires and asserts each one is packaged.
 */
const HERE = dirname(fileURLToPath(import.meta.url));

function localRequiresOf(file) {
  const source = readFileSync(resolve(HERE, file), "utf8");
  return [...source.matchAll(/require\("\.\/([^"]+)"\)/g)].map(([, name]) =>
    name.endsWith(".js") ? name : `${name}.js`
  );
}

describe("electron-builder files allowlist", () => {
  const packageJson = JSON.parse(readFileSync(resolve(HERE, "package.json"), "utf8"));
  const files = packageJson.build.files;

  it("includes every local module main.js requires", () => {
    const required = localRequiresOf("main.js");

    expect(required.length).toBeGreaterThan(0);
    for (const name of required) {
      expect(files, `main.js requires ./${name} but it is not in build.files`).toContain(name);
    }
  });

  it("still packages the preload scripts both windows load", () => {
    expect(files).toContain("preload.js");
  });

  it("keeps test files out of the installer", () => {
    expect(files).toContain("!src/**/*.test.js");
    // Root-level tests are excluded by omission - they must never be
    // added to the allowlist by accident.
    expect(files).not.toContain("backend-manager.test.js");
    expect(files).not.toContain("update-manager.test.js");
    expect(files).not.toContain("packaging.test.js");
  });
});
