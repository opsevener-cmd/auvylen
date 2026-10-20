import zh from "./zh-CN.json";
export type Locale = "en" | "zh-CN";
export const localeCookie = "auvylen_language";
export function chooseLocale(saved?: string, accepted = ""): Locale {
  if (saved === "en" || saved === "zh-CN") return saved;
  const choices = accepted.split(",").map((part, index) => {
    const [language, ...parameters] = part.trim().toLowerCase().split(";");
    const quality = parameters.map(value => value.trim()).find(value => value.startsWith("q="));
    return {language: language.trim(), quality: quality === undefined ? 1 : Number(quality.slice(2)), index};
  }).filter(item => item.quality > 0 && item.quality <= 1)
    .sort((a, b) => b.quality - a.quality || a.index - b.index);
  for (const {language} of choices) {
    if (language === "zh" || language.startsWith("zh-")) return "zh-CN";
    if (language === "en" || language.startsWith("en-")) return "en";
  }
  return "en";
}
export function translate(locale: Locale, key: string, values?: Record<string, string | number>): string {
  const message = locale === "zh-CN" ? (zh as Record<string, string>)[key] ?? key : key;
  return message.replace(/\{(\w+)\}/g, (token, name: string) => values?.[name] === undefined ? token : String(values[name]));
}
