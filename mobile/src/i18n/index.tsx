import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { en } from './en';
import { zhCN } from './zhCN';
import { zhHK } from './zhHK';

export type Language = 'en' | 'zh-CN' | 'zh-HK';
export type TranslationKey = keyof typeof en;
export type Translate = (key: TranslationKey, vars?: Record<string, string | number>) => string;

export const LANGUAGE_STORAGE_KEY = 'bt:language';

const catalogs: Record<Language, Record<TranslationKey, string>> = {
  en,
  'zh-CN': zhCN,
  'zh-HK': zhHK,
};

function isLanguage(value: string | null): value is Language {
  return value === 'en' || value === 'zh-CN' || value === 'zh-HK';
}

function translate(
  language: Language,
  key: TranslationKey,
  vars?: Record<string, string | number>,
) {
  const text = catalogs[language][key] ?? en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name: string) => String(vars?.[name] ?? `{${name}}`));
}

export function localeFor(language: Language): 'en-HK' | 'zh-CN' | 'zh-HK' {
  if (language === 'zh-HK') return 'zh-HK';
  if (language === 'zh-CN') return 'zh-CN';
  return 'en-HK';
}

// Translated API event type, falling back to the raw type for unknown values.
export function eventLabel(t: Translate, type: string): string {
  const key = `event_${type}`;
  return key in en ? t(key as TranslationKey) : type;
}

// Translated trend ('improving' | 'stable' | 'worsening'), falling back to the raw value.
export function trendLabel(t: Translate, trend: string): string {
  const key = `trend_${trend}`;
  return key in en ? t(key as TranslationKey) : trend;
}

interface LanguageContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: Translate;
}

const LanguageContext = createContext<LanguageContextValue>({
  language: 'en',
  setLanguage: () => {},
  t: (key, vars) => translate('en', key, vars),
});

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>('en');
  // Set once the user picks, so a late AsyncStorage load cannot overwrite their choice
  const touchedRef = useRef(false);

  useEffect(() => {
    AsyncStorage.getItem(LANGUAGE_STORAGE_KEY)
      .then((saved) => {
        if (!touchedRef.current && isLanguage(saved)) setLanguageState(saved);
      })
      .catch((err) => console.warn('Could not read language', err));
  }, []);

  const setLanguage = useCallback((next: Language) => {
    touchedRef.current = true;
    setLanguageState(next);
    AsyncStorage.setItem(LANGUAGE_STORAGE_KEY, next).catch((err) =>
      console.warn('Could not save language', err),
    );
  }, []);

  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      setLanguage,
      t: (key, vars) => translate(language, key, vars),
    }),
    [language, setLanguage],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext);
}
