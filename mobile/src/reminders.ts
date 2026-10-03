import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';

export const REMINDER_KEY = 'bt:reminder';
const CHANNEL_ID = 'reminders';
const DEFAULT_HOUR = 8;
const DEFAULT_MINUTE = 0;

export interface ReminderSettings {
  enabled: boolean;
  hour: number;
  minute: number;
}

export const DEFAULT_REMINDER: ReminderSettings = {
  enabled: false,
  hour: DEFAULT_HOUR,
  minute: DEFAULT_MINUTE,
};

// Local notifications only; expo-notifications scheduling is unavailable on web.
export const remindersSupported = Platform.OS !== 'web';

const inRange = (n: unknown, max: number): n is number =>
  typeof n === 'number' && Number.isInteger(n) && n >= 0 && n <= max;

export async function loadReminder(): Promise<ReminderSettings> {
  const raw = await AsyncStorage.getItem(REMINDER_KEY);
  if (!raw) return DEFAULT_REMINDER;
  try {
    const v = JSON.parse(raw) as Partial<ReminderSettings>;
    if (inRange(v.hour, 23) && inRange(v.minute, 59)) {
      return { enabled: v.enabled === true, hour: v.hour, minute: v.minute };
    }
  } catch {
    // Corrupt value: fall through to the defaults.
  }
  return DEFAULT_REMINDER;
}

export const saveReminder = (settings: ReminderSettings) =>
  AsyncStorage.setItem(REMINDER_KEY, JSON.stringify(settings));

// Foreground suppression is intended: no notification handler is set, so nothing shows while
// the app is open.

// True when notifications are allowed. Prompts only if the OS still lets us ask.
export async function ensurePermission(): Promise<boolean> {
  if (!remindersSupported) return false;
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync(CHANNEL_ID, {
      name: CHANNEL_ID,
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }
  const current = await Notifications.getPermissionsAsync();
  if (current.granted) return true;
  if (!current.canAskAgain) return false;
  return (await Notifications.requestPermissionsAsync()).granted;
}

// All native notification calls run one at a time, in call order. The chain never rejects.
let queue: Promise<unknown> = Promise.resolve();
const run = <T>(fn: () => Promise<T>): Promise<T> => {
  const result = queue.then(fn);
  queue = result.catch(() => undefined);
  return result;
};

// Bumped by clearReminder so syncs queued before a deletion are skipped.
let epoch = 0;

export interface ReminderPlan {
  settings: ReminderSettings;
  title: string;
  body: string;
}

// Make the OS schedule match the latest plan (null = no reminder). The app owns exactly one
// scheduled notification, so replace everything. getLatest is read when the task runs, so a stale
// call applies the newest state and rapid changes end with exactly the final one.
export function syncReminder(getLatest: () => ReminderPlan | null): Promise<void> {
  if (!remindersSupported) return Promise.resolve();
  const mine = epoch;
  return run(async () => {
    if (mine !== epoch) return;
    await Notifications.cancelAllScheduledNotificationsAsync();
    const plan = getLatest();
    if (!plan || !plan.settings.enabled) return;
    await Notifications.scheduleNotificationAsync({
      content: { title: plan.title, body: plan.body },
      trigger: {
        hour: plan.settings.hour,
        minute: plan.settings.minute,
        repeats: true,
        channelId: CHANNEL_ID,
      },
    });
  });
}

// Used after "Delete all my data": cancel the notification and drop the stored setting.
export async function clearReminder(): Promise<void> {
  epoch += 1;
  try {
    if (remindersSupported) await run(() => Notifications.cancelAllScheduledNotificationsAsync());
  } catch (err) {
    console.warn('Could not cancel the reminder', err);
  }
  await AsyncStorage.removeItem(REMINDER_KEY);
}
