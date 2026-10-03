import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useLanguage } from './i18n';
import { API_BASE_URL } from './config';
import { registerDriver, giveConsent } from './api/client';

const STORAGE_KEYS = {
  DRIVER_ID: 'drivescore:driver_id',
  API_KEY: 'drivescore:api_key',
  ONBOARDED: 'bt:onboarded',
};

export type SessionStatus = 'loading' | 'onboarding' | 'ready';

interface Session {
  status: SessionStatus;
  apiKey: string | null;
  failed: boolean;
  retry: () => void;
  completeOnboarding: () => Promise<void>;
}

async function registerAndConsent(): Promise<{ driverId: string; apiKey: string }> {
  const response = await registerDriver();
  await giveConsent(response.api_key);
  return { driverId: response.driver_id, apiKey: response.api_key };
}

async function persist(driverId: string, apiKey: string): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEYS.DRIVER_ID, driverId);
  await AsyncStorage.setItem(STORAGE_KEYS.API_KEY, apiKey);
  await AsyncStorage.setItem(STORAGE_KEYS.ONBOARDED, 'true');
}

interface Resolved {
  status: 'onboarding' | 'ready';
  apiKey: string | null;
  storedKey: string | null;
}

async function resolveSession(): Promise<Resolved> {
  const driverId = await AsyncStorage.getItem(STORAGE_KEYS.DRIVER_ID);
  const key = await AsyncStorage.getItem(STORAGE_KEYS.API_KEY);
  const onboarded = (await AsyncStorage.getItem(STORAGE_KEYS.ONBOARDED)) === 'true';
  const storedKey = driverId && key ? key : null;
  if (!onboarded) return { status: 'onboarding', apiKey: null, storedKey };
  if (storedKey) return { status: 'ready', apiKey: storedKey, storedKey };
  // Consent was given earlier but credentials are gone: re-register silently.
  const creds = await registerAndConsent();
  await persist(creds.driverId, creds.apiKey);
  return { status: 'ready', apiKey: creds.apiKey, storedKey: null };
}

// `bt:onboarded` is the only consent marker. Stored credentials alone (old flow wrote them
// before any checkbox) send the user through onboarding; the final step then only re-sends
// consent for the stored key. No data is accepted before consent.
export function useSession(): Session {
  const { t } = useLanguage();
  const tRef = useRef(t);
  tRef.current = t;
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const storedKey = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      setFailed(false);
      try {
        const res = await resolveSession();
        storedKey.current = res.storedKey;
        if (cancelled) return;
        if (res.apiKey) setApiKey(res.apiKey);
        setStatus(res.status);
      } catch {
        if (cancelled) return;
        setFailed(true);
        setStatus('ready');
        Alert.alert(
          tRef.current('setupErrorTitle'),
          tRef.current('setupErrorBody', { url: API_BASE_URL }),
        );
      }
    };
    init();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  // Credentials and the flag are stored only after consent succeeds. Throws on failure; the
  // screen shows the error.
  const completeOnboarding = useCallback(async () => {
    let key = storedKey.current;
    if (key) {
      await giveConsent(key);
      await AsyncStorage.setItem(STORAGE_KEYS.ONBOARDED, 'true');
    } else {
      const creds = await registerAndConsent();
      await persist(creds.driverId, creds.apiKey);
      key = creds.apiKey;
    }
    setApiKey(key);
    setStatus('ready');
  }, []);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { status, apiKey, failed, retry, completeOnboarding };
}
