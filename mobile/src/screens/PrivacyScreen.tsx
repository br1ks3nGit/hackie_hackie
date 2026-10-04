import React, { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  findNodeHandle,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { theme } from '../theme';
import { useLanguage } from '../i18n';
import { styles as shared } from '../appStyles';
import { Card, PageHeader, PrimaryButton, SecondaryButton } from '../ui';
import { ErrorBanner } from '../uiBlocks';
import { ReminderCard } from '../ReminderCard';
import { deleteMe } from '../api/client';

interface PrivacyScreenProps {
  apiKey: string | null;
  recording: boolean;
  onDeleted: () => Promise<void>;
}

// 401: the key no longer maps to a driver (already erased), so treat as deleted.
const isAlreadyGone = (err: unknown) =>
  typeof (err as { status?: unknown }).status === 'number' &&
  (err as { status: number }).status === 401;

// Server erasure first; local data is cleared (onDeleted) only after it succeeds.
function useDeleteAll({
  apiKey,
  busy,
  onDeleted,
}: Pick<PrivacyScreenProps, 'apiKey' | 'onDeleted'> & { busy: boolean }) {
  const { t } = useLanguage();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [failed, setFailed] = useState(false);
  const busyRef = useRef(false);

  const finish = async () => {
    AccessibilityInfo.announceForAccessibility(t('deletionDone'));
    // Session state is already reset by onDeleted; only storage cleanup can fail here.
    try {
      await onDeleted();
    } catch (err) {
      console.warn('Could not clear local data after deletion; retrying', err);
      try {
        await onDeleted();
      } catch (retryErr) {
        console.warn('Local data cleanup failed again', retryErr);
      }
    }
  };

  const confirm = async () => {
    if (busyRef.current || busy || !apiKey) return;
    busyRef.current = true;
    setDeleting(true);
    setFailed(false);
    try {
      await deleteMe(apiKey);
    } catch (err) {
      if (!isAlreadyGone(err)) {
        setFailed(true);
        AccessibilityInfo.announceForAccessibility(t('deleteError'));
        busyRef.current = false;
        setDeleting(false);
        return;
      }
    }
    await finish();
  };

  const cancel = () => {
    setConfirming(false);
    setFailed(false);
  };
  return { confirming, setConfirming, deleting, failed, confirm, cancel };
}

export function PrivacyScreen({ apiKey, recording, onDeleted }: PrivacyScreenProps) {
  const { t } = useLanguage();
  const del = useDeleteAll({ apiKey, busy: recording, onDeleted });
  const questionRef = useRef<Text>(null);
  const { confirming } = del;
  useEffect(() => {
    if (!confirming) return;
    const node = findNodeHandle(questionRef.current);
    if (node) AccessibilityInfo.setAccessibilityFocus(node);
  }, [confirming]);
  const hint = recording ? t('stopRecordingFirst') : undefined;
  return (
    <ScrollView style={shared.screen} contentContainerStyle={[shared.content, styles.content]}>
      <PageHeader title={t('privacy')} />
      <Card>
        <Text style={shared.bodyStrong} accessibilityRole="header">
          {t('dataTitle')}
        </Text>
        <Text style={styles.body}>{t('dataBody')}</Text>
      </Card>
      <ReminderCard />
      <View accessibilityLiveRegion="polite">
        {recording ? (
          <View style={styles.notice}>
            <Text style={styles.noticeText}>{t('stopRecordingFirst')}</Text>
          </View>
        ) : null}
      </View>
      {del.failed ? (
        <ErrorBanner text={t('deleteError')} onRetry={recording ? undefined : del.confirm} />
      ) : null}
      {del.confirming ? (
        <Card>
          <Text ref={questionRef} style={shared.bodyStrong} accessibilityRole="header">
            {t('deleteQuestion')}
          </Text>
          <Text style={styles.body}>{t('deleteWarning')}</Text>
          <PrimaryButton
            danger
            style={styles.gap}
            label={del.deleting ? t('deleting') : t('delete')}
            disabled={del.deleting || recording}
            accessibilityHint={hint}
            onPress={del.confirm}
          />
          <SecondaryButton
            style={styles.gap}
            label={t('cancel')}
            disabled={del.deleting}
            onPress={del.cancel}
          />
        </Card>
      ) : (
        <SecondaryButton
          label={t('deleteAll')}
          disabled={recording || !apiKey}
          accessibilityHint={hint}
          onPress={() => del.setConfirming(true)}
        />
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { gap: theme.space.lg, paddingBottom: theme.space.xl },
  body: {
    ...theme.type.body,
    color: theme.colors.ink,
    marginTop: theme.space.sm,
  },
  gap: { marginTop: theme.space.md },
  notice: {
    backgroundColor: theme.colors.warning.soft,
    borderRadius: theme.radii.cardSm,
    padding: theme.space.md,
  },
  noticeText: { ...theme.type.bodyStrong, color: theme.colors.warning.ink },
});
