import {describe, expect, it} from "vitest";
import {chooseLocale, translate} from "./catalog";
import zh from "./zh-CN.json";
describe("locale negotiation and resources", () => {
  it("prioritizes saved choices, respects browser quality and falls back safely", () => {
    expect(chooseLocale("en", "zh-CN")).toBe("en");
    expect(chooseLocale(undefined, "zh-CN,zh;q=0.9,en;q=0.8")).toBe("zh-CN");
    expect(chooseLocale(undefined, "zh-CN;q=0.2,en;q=0.9")).toBe("en");
    expect(chooseLocale(undefined, "en;q=0,zh;q=0.5")).toBe("zh-CN");
    expect(chooseLocale("invalid", "fr-FR")).toBe("en");
  });
  it("localizes critical workflows while preserving interpolated user data", () => {
    for (const key of ["Sign in", "Personal preference datasets", "Upload photographs", "Save and next", "Left preferred", "Train new version", "Predict personal rating", "Owner workspace", "Redeem Code", "Development / Synthetic Result"]) expect(translate("zh-CN", key)).not.toBe(key);
    expect(translate("zh-CN", "Disable account {name}", {name: "ORIGIN"})).toBe("停用账户 ORIGIN");
    expect(translate("en", "Disable account {name}", {name: "ORIGIN"})).toBe("Disable account ORIGIN");
  });
  it("keeps interpolation tokens aligned in every translation", () => {
    for (const [key, value] of Object.entries(zh)) {
      expect(value.trim().length, key).toBeGreaterThan(0);
      expect(value.match(/\{\w+\}/g)?.sort() ?? [], key).toEqual(key.match(/\{\w+\}/g)?.sort() ?? []);
    }
  });
});

it("respects whitespace and explicit q=0 in browser language preferences", () => {
  expect(chooseLocale(undefined, "zh-CN; q=0, en; q=0.8")).toBe("en");
});

// Catch missing translations when a new static label is added to any page/component.
it("covers every literal translation key used by the UI", async () => {
  const {readdir, readFile} = await import("node:fs/promises");
  const {fileURLToPath} = await import("node:url");
  const path = await import("node:path");
  const sourceRoot = fileURLToPath(new URL("../../", import.meta.url));
  async function inspect(directory: string): Promise<void> {
    for (const entry of await readdir(directory, {withFileTypes: true})) {
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) {await inspect(file); continue;}
      if (!file.endsWith(".tsx")) continue;
      const source = await readFile(file, "utf8");
      // Static calls use double-quoted English keys; dynamic keys are covered above.
      const keys = source.matchAll(/(?:\bt\(|<Text>\{)("(?:[^"\\]|\\.)*")/g);
      for (const match of keys) {
        const key = JSON.parse(match[1]) as string;
        expect(Object.hasOwn(zh, key), `${file}: ${key}`).toBe(true);
      }
    }
  }
  await inspect(sourceRoot);
});
