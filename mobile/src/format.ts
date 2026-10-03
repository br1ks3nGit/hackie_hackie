import { Language, localeFor } from './i18n';

export function formatTime(iso: string, language: Language): string {
  return new Date(iso).toLocaleTimeString(localeFor(language), {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatDate(iso: string, language: Language): string {
  return new Date(iso).toLocaleDateString(localeFor(language), {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}

export function formatDateTime(iso: string, language: Language): string {
  return `${formatDate(iso, language)} ${formatTime(iso, language)}`;
}
