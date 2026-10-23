import { applyDocumentLocale, LOCALE_ENDONYMS } from "@clawk/shared/i18n";
import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useMemo,
  type ReactNode,
} from "react";
import type { Locale, Translations } from "./types";

// English + Spanish ship in the main bundle as synchronous fallbacks (English is
// the universal default; Spanish is the LATAM default, so neither flashes on
// first paint). Every OTHER locale is code-split and loaded on demand the first
// time it's selected — see LOADERS — so we don't ship ~14 translation files no
// one reads on first paint (they were ~70-100KB of dead weight in the bundle).
import { en } from "./en";
import { es } from "./es";

// Lazy loaders for the non-default locales. Each resolves to its named export.
const LOADERS: Partial<Record<Locale, () => Promise<Translations>>> = {
  zh: () => import("./zh").then((m) => m.zh),
  "zh-hant": () => import("./zh-hant").then((m) => m.zhHant),
  ja: () => import("./ja").then((m) => m.ja),
  de: () => import("./de").then((m) => m.de),
  fr: () => import("./fr").then((m) => m.fr),
  tr: () => import("./tr").then((m) => m.tr),
  uk: () => import("./uk").then((m) => m.uk),
  af: () => import("./af").then((m) => m.af),
  ko: () => import("./ko").then((m) => m.ko),
  it: () => import("./it").then((m) => m.it),
  ga: () => import("./ga").then((m) => m.ga),
  pt: () => import("./pt").then((m) => m.pt),
  ru: () => import("./ru").then((m) => m.ru),
  hu: () => import("./hu").then((m) => m.hu),
  ar: () => import("./ar").then((m) => m.ar),
};

// Cache of already-resolved translation objects, seeded with the eager locales.
const LOADED: Partial<Record<Locale, Translations>> = { en, es };

// Source of truth for the supported locale set, in picker order. It's tiny and
// always loaded, unlike the translation objects.
const SUPPORTED_LOCALES: Locale[] = [
  "en",
  "zh",
  "zh-hant",
  "ja",
  "de",
  "es",
  "fr",
  "tr",
  "uk",
  "af",
  "ko",
  "it",
  "ga",
  "pt",
  "ru",
  "hu",
  "ar",
];

// Display metadata for the language picker — endonyms from @clawk/shared so the
// desktop and web pickers can never disagree on a language's native name.
export const LOCALE_META: Record<Locale, { name: string }> = Object.fromEntries(
  SUPPORTED_LOCALES.map((id) => [id, { name: LOCALE_ENDONYMS[id] }]),
) as Record<Locale, { name: string }>;

const STORAGE_KEY = "clawk-locale";

function isLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as string[]).includes(value);
}

function getInitialLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && isLocale(stored)) return stored;
    // No explicit choice yet: follow the browser's language so Spanish-first
    // (LATAM) users land on Spanish without hunting for the switcher. Maps
    // e.g. "es-AR" -> "es"; falls back to English for unsupported languages.
    const nav =
      (navigator.languages && navigator.languages[0]) || navigator.language || "";

    const base = nav.toLowerCase().split("-")[0];

    if (base && isLocale(base)) return base as Locale;
  } catch {
    // SSR or privacy mode
  }
  return "en";
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: Translations;
}

const I18nContext = createContext<I18nContextValue>({
  locale: "en",
  setLocale: () => {},
  t: en,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);

  // `t` is the active, ALWAYS-COMPLETE translation object. It starts at whatever
  // is already cached for the initial locale (en/es), else English, so it is
  // never partial. Non-eager locales are loaded by the effect below and swapped
  // in once ready (a brief English render for those is acceptable on first use).
  const [t, setT] = useState<Translations>(() => LOADED[locale] ?? en);

  useEffect(() => {
    const cached = LOADED[locale];
    if (cached) {
      setT(cached);
      return;
    }
    const loader = LOADERS[locale];
    if (!loader) {
      setT(en);
      return;
    }
    let cancelled = false;
    void loader()
      .then((mod) => {
        LOADED[locale] = mod;
        if (!cancelled) setT(mod);
      })
      .catch(() => {
        // Keep the current (fallback) translations if the chunk fails to load.
      });
    return () => {
      cancelled = true;
    };
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    applyDocumentLocale(locale);
  }, [locale]);

  const value = useMemo<I18nContextValue>(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
