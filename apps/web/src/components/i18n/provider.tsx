"use client";
import {createContext, useCallback, useContext, useMemo, useState} from "react";
import {localeCookie, translate, type Locale} from "@/lib/i18n/catalog";
const Context = createContext({locale: "en" as Locale, setLocale: (_locale: Locale) => {void _locale;}});
export function LanguageProvider({initialLocale, children}: {initialLocale: Locale; children: React.ReactNode}) {
  const [locale, updateLocale] = useState(initialLocale);
  const setLocale = useCallback((value: Locale) => {
    document.cookie = `${localeCookie}=${value}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
    document.documentElement.lang = value;
    document.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("input, select, textarea").forEach(field => field.setCustomValidity(""));
    updateLocale(value);
  }, []);
  const context = useMemo(() => ({locale, setLocale}), [locale, setLocale]);
  return <Context.Provider value={context}><div className="app-frame" onInputCapture={event => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement || event.target instanceof HTMLTextAreaElement) event.target.setCustomValidity("");
  }} onInvalidCapture={event => {
    const field = event.target;
    if (!(field instanceof HTMLInputElement || field instanceof HTMLSelectElement || field instanceof HTMLTextAreaElement)) return;
    field.setCustomValidity("");
    const validity = field.validity;
    const key = validity.valueMissing ? "Complete this required field." : validity.typeMismatch ? "Enter a valid value in the requested format." : validity.rangeUnderflow || validity.rangeOverflow ? "Enter a value between {min} and {max}." : validity.tooShort || validity.tooLong ? "Use between {min} and {max} characters." : "Check this field and try again.";
    field.setCustomValidity(translate(locale, key, {min: field.getAttribute("min") ?? field.getAttribute("minlength") ?? 0, max: field.getAttribute("max") ?? field.getAttribute("maxlength") ?? "—"}));
  }}>{children}</div></Context.Provider>;
}
export function useI18n() {
  const context = useContext(Context);
  const t = useCallback((key: string, values?: Record<string, string | number>) => translate(context.locale, key, values), [context.locale]);
  return {...context, t};
}
/** Small client boundary also keeps server-rendered result/status copy switchable. */
export function Text({children, values}: {children: string; values?: Record<string, string | number>}) {
  const {t} = useI18n();
  return <>{t(children, values)}</>;
}
