import React, { useCallback, useEffect } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { theme } from '../theme';
import { useLanguage } from '../i18n';
import { styles as shared } from '../appStyles';
import { PageHeader } from '../ui';
import { ErrorBanner, LoadingBlock } from '../uiBlocks';
import { useRecording } from '../useRecording';
import { useHomeData } from './useHomeData';
import { TripRow } from './TripRow';
import { ConfirmCard, RecordingCard, ScoreCard, StatRow, messageFor } from './homeParts';

const RECENT_COUNT = 3;

interface HomeScreenProps {
  apiKey: string | null;
  active: boolean;
  onViewAll: () => void;
  onOpenTrip: (tripId: string) => void;
  setupFailed: boolean;
  onRetrySetup: () => void;
  onTripProcessed: () => void;
  onRecordingChange: (recording: boolean) => void;
}

export function HomeScreen(props: HomeScreenProps) {
  const { apiKey, active, onViewAll, onOpenTrip, setupFailed, onRetrySetup } = props;
  const { t } = useLanguage();
  const data = useHomeData(apiKey, active, setupFailed);
  const { refresh } = data;
  const { onTripProcessed } = props;
  const processed = useCallback(() => {
    refresh();
    onTripProcessed();
  }, [refresh, onTripProcessed]);
  const rec = useRecording(apiKey, processed);
  const { onRecordingChange } = props;
  const { busy } = rec;
  useEffect(() => onRecordingChange(busy), [busy, onRecordingChange]);
  const message = messageFor(t, data);
  const recent = data.trips.slice(0, RECENT_COUNT);
  const showSkeleton = data.loading && data.summary === null && !setupFailed;
  return (
    <ScrollView style={shared.screen} contentContainerStyle={[shared.content, styles.body]}>
      <PageHeader eyebrow={t('visitorCover')} title={t('appName')} />
      {setupFailed && !apiKey ? (
        <ErrorBanner text={t('setupFailed')} onRetry={onRetrySetup} />
      ) : null}
      {data.loadError ? <ErrorBanner text={t('loadError')} onRetry={data.refresh} /> : null}
      {message ? (
        <View
          style={data.labelError ? styles.messageError : styles.messageOk}
          accessibilityRole={data.labelError ? 'alert' : undefined}
          accessibilityLiveRegion="polite"
        >
          <Text style={data.labelError ? styles.messageErrorText : styles.messageOkText}>
            {message}
          </Text>
        </View>
      ) : null}
      {showSkeleton ? <LoadingBlock /> : <ScoreCard summary={data.summary} />}
      {showSkeleton ? null : <StatRow summary={data.summary} />}
      <RecordingCard
        recording={rec.recording}
        inTrip={rec.inTrip}
        drivingMode={rec.drivingMode}
        chunkCount={rec.chunkCount}
        tripId={rec.currentTripId}
        onToggleRecording={rec.toggleRecording}
        onDrivingMode={rec.changeDrivingMode}
      />
      {data.toConfirm.length > 0 ? (
        <ConfirmCard
          trips={data.toConfirm}
          labelling={data.labelling}
          onConfirm={data.confirmTrip}
        />
      ) : null}
      {recent.length > 0 ? (
        <View style={styles.recent}>
          <View style={styles.recentHeader}>
            <Text style={styles.recentTitle} accessibilityRole="header">
              {t('recentTrips')}
            </Text>
            <Pressable
              style={styles.link}
              onPress={onViewAll}
              accessibilityRole="button"
              accessibilityLabel={t('viewAll')}
            >
              <Text style={styles.linkText}>{t('viewAll')}</Text>
            </Pressable>
          </View>
          {recent.map((trip) => (
            <TripRow key={trip.trip_id} trip={trip} onPress={() => onOpenTrip(trip.trip_id)} />
          ))}
        </View>
      ) : null}
    </ScrollView>
  );
}

const { colors, radii, space, type } = theme;

const styles = StyleSheet.create({
  body: { gap: space.lg, paddingBottom: space.xl },
  recent: { gap: space.md },
  recentHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  recentTitle: { ...type.bodyStrong, color: colors.ink },
  link: { minHeight: theme.minTouch, minWidth: theme.minTouch, justifyContent: 'center' },
  linkText: { ...type.bodyStrong, color: colors.jadeInk },
  messageOk: { backgroundColor: colors.success.soft, borderRadius: radii.cardSm, padding: space.lg },
  messageOkText: { ...type.body, color: colors.success.ink },
  messageError: { backgroundColor: colors.danger.soft, borderRadius: radii.cardSm, padding: space.lg },
  messageErrorText: { ...type.body, color: colors.danger.ink },
});
