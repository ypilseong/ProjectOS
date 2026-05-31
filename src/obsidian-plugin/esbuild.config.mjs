import esbuild from "esbuild";
import process from "process";
import builtins from "builtin-modules";
import esbuildSvelte from "esbuild-svelte";
import { sveltePreprocess } from "svelte-preprocess";

const prod = process.argv[2] === "production";

const context = await esbuild.context({
  banner: {
    js: "/* ProjectOS Vault Sync */",
  },
  bundle: true,
  entryPoints: ["src/main.ts"],
  external: [
    "obsidian",
    "electron",
    "@codemirror/autocomplete",
    "@codemirror/collab",
    "@codemirror/commands",
    "@codemirror/language",
    "@codemirror/lint",
    "@codemirror/search",
    "@codemirror/state",
    "@codemirror/view",
    "@lezer/common",
    "@lezer/highlight",
    "@lezer/lr",
    ...builtins,
  ],
  plugins: [
    esbuildSvelte({
      compilerOptions: { css: "injected" },
      preprocess: sveltePreprocess(),
    }),
  ],
  format: "cjs",
  logLevel: "info",
  minify: prod,
  outfile: "main.js",
  platform: "browser",
  sourcemap: prod ? false : "inline",
  target: "es2018",
  treeShaking: true,
  mainFields: ["svelte", "browser", "module", "main"],
  conditions: ["svelte", "browser"],
});

if (prod) {
  await context.rebuild();
  await context.dispose();
} else {
  await context.watch();
}
