import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Linking, Platform, Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import DateTimePicker, {
  DateTimePickerAndroid,
  DateTimePickerEvent,
} from '@react-native-community/datetimepicker';
import { theme, switchColors } from './theme';
import { localeFor, useLanguage } from './i18n';
import { styles as shared } from './appStyles';
import { Card, Inset, SecondaryButton } from './ui';
import {
  DEFAULT_REMINDER,
  ReminderPlan,
  ReminderSettings,
  ensurePermission,
  loadReminder,
  remindersSupported,
  saveReminder,
  syncReminder,
} from './reminders';

const atTime = (hour: number, minute: number) => {
  const d = new Date();
  d.setHours(hour, minute, 0, 0);
  return d;
};

// Persisted settings plus the OS schedule; permission is requested only when turning on.
function useReminder() {
  const { language, t } = useLanguage();
  const [settings, setSettings] = useState<ReminderSettings>(DEFAULT_REMINDER);
  const [loaded, setLoaded] = useState(false);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    loadReminder()
      .then(setSettings)
      .catch((err) => console.warn('Could not read reminder', err))
      .finally(() => setLoaded(true));
  }, []);

  const planRef = useRef<ReminderPlan | null>(null);
  planRef.current = { settings, title: t('reminderTitle'), body: t('reminderBody') };

  // Reconcile the OS schedule on enable/disable, time change, and language change.
  useEffect(() => {
    if (!loaded) return;
    syncReminder(() => planRef.current).catch((err) =>
      console.warn('Could not schedule reminder', err),
    );
  }, [loaded, settings, t]);

  const update = useCallback((next: ReminderSettings) => {
    setSettings(next);
    saveReminder(next).catch((err) => console.warn('Could not save reminder', err));
  }, []);

  const setEnabled = async (on: boolean) => {
    if (!on) {
      setDenied(false);
      update({ ...settings, enabled: false });
      return;
    }
    const granted = await ensurePermission().catch(() => false);
    setDenied(!granted);
    if (!granted) AccessibilityInfo.announceForAccessibility(t('reminderDenied'));
    if (granted) update({ ...settings, enabled: true });
  };

  const setTime = (hour: number, minute: number) => update({ ...settings, hour, minute });
  return { settings, denied, setEnabled, setTime };
}

export function ReminderCard() {
  const { t, language } = useLanguage();
  const { settings, denied, setEnabled, setTime } = useReminder();
  const [iosOpen, setIosOpen] = useState(false);
  const active = remindersSupported && settings.enabled;
  const time = atTime(settings.hour, settings.minute);
  const label = time.toLocaleTimeString(localeFor(language), {
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });

  const onPicked = (event: DateTimePickerEvent, date?: Date) => {
    if (event.type !== 'set' || !date) return;
    setTime(date.getHours(), date.getMinutes());
  };
  const openPicker = () => {
    if (Platform.OS === 'android') {
      DateTimePickerAndroid.open({ value: time, mode: 'time', is24Hour: true, onChange: onPicked });
    } else {
      setIosOpen((v) => !v);
    }
  };

  return (
    <Card>
      <Text style={shared.bodyStrong} accessibilityRole="header">
        {t('reminders')}
      </Text>
      <Text style={styles.caption}>{t('remindersDetail')}</Text>
      <View style={styles.switchRow}>
        <Text style={[shared.body, styles.flex]}>{t('reminderToggle')}</Text>
        <Switch
          value={settings.enabled}
          onValueChange={setEnabled}
          disabled={!remindersSupported}
          accessibilityRole="switch"
          accessibilityLabel={t('reminderToggle')}
          accessibilityState={{ checked: settings.enabled, disabled: !remindersSupported }}
          trackColor={{ true: switchColors.on, false: switchColors.off }}
          thumbColor={switchColors.thumb}
        />
      </View>
      {settings.enabled ? <Text style={styles.caption}>{t('reminderOn')}</Text> : null}
      <Text style={styles.caption}>
        {remindersSupported ? t('reminderWhy') : t('reminderNotOnWeb')}
      </Text>
      {remindersSupported ? (
        <Inset style={[styles.field, !active && styles.fieldOff]}>
          <Pressable
            style={styles.fieldPress}
            disabled={!active}
            onPress={openPicker}
            accessibilityRole="button"
            accessibilityLabel={`${t('reminderTime')}, ${label}`}
            accessibilityState={{ disabled: !active, expanded: Platform.OS === 'ios' ? iosOpen : undefined }}
          >
            <Text style={[shared.body, styles.flex]}>{t('reminderTime')}</Text>
            <Text style={shared.bodyStrong}>{label}</Text>
          </Pressable>
        </Inset>
      ) : null}
      {active && iosOpen && Platform.OS === 'ios' ? (
        <DateTimePicker value={time} mode="time" display="spinner" is24Hour onChange={onPicked} />
      ) : null}
      <View accessibilityLiveRegion="polite">
        {denied ? (
          <View style={styles.notice}>
            <Text style={styles.noticeText}>{t('reminderDenied')}</Text>
            <SecondaryButton
              style={styles.action}
              label={t('openSettings')}
              onPress={() => Linking.openSettings()}
            />
          </View>
        ) : null}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  caption: { ...theme.type.caption, color: theme.colors.textMuted, marginTop: theme.space.sm },
  switchRow: {
    minHeight: theme.minSwitchRow,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.space.md,
    marginTop: theme.space.sm,
  },
  flex: { flex: 1, flexShrink: 1 },
  field: { marginTop: theme.space.md },
  fieldOff: { opacity: theme.disabledOpacity },
  fieldPress: {
    minHeight: theme.minSwitchRow,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: theme.space.md,
    flexWrap: 'wrap',
    gap: theme.space.sm,
  },
  notice: {
    backgroundColor: theme.colors.warning.soft,
    borderRadius: theme.radii.cardSm,
    padding: theme.space.md,
    marginTop: theme.space.md,
  },
  noticeText: { ...theme.type.bodyStrong, color: theme.colors.warning.ink },
  action: { marginTop: theme.space.md, alignSelf: 'center' },
});
