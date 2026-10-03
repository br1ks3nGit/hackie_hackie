import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { theme } from '../theme';
import { useLanguage, eventLabel, Translate } from '../i18n';
import { styles as shared } from '../appStyles';
import { formatDateTime } from '../format';
import { Card, PageHeader, ScoreBar, StatTile } from '../ui';
import { ErrorBanner, LoadingBlock, TierChip } from '../uiBlocks';
import { getTripDetail, TripDetailResponse } from '../api/client';

const { colors, radii, space, type } = theme;
const HARSH_TYPES = ['harsh_brake', 'harsh_accel', 'sharp_corner', 'speeding', 'crash'];
const DOT = 10;
const FONT_STACK_SCALE = 1.3;

function countOf(trip: TripDetailResponse, type: string): number {
  return trip.events.filter((e) => e.type === type).length;
}

function tiles(t: Translate, trip: TripDetailResponse) {
  const peak = Math.max(0, ...trip.events.map((e) => e.peak_g ?? 0));
  return [
    { label: t('distance'), value: t('kmValue', { km: trip.distance_km.toFixed(1) }) },
    { label: t('duration'), value: trip.duration_min === null ? '-' : t('minValue', { min: trip.duration_min.toFixed(0) }) },
    { label: t('hardBrakes'), value: countOf(trip, 'harsh_brake') },
    { label: t('hardAccel'), value: countOf(trip, 'harsh_accel') },
    { label: t('sharpCorners'), value: countOf(trip, 'sharp_corner') },
    { label: t('peakG'), value: peak.toFixed(2) },
  ];
}

function TileGrid({ trip }: { trip: TripDetailResponse }) {
  const { t } = useLanguage();
  const all = tiles(t, trip);
  const { fontScale } = useWindowDimensions();
  const cols = fontScale > FONT_STACK_SCALE ? 1 : 2;
  const rows = Array.from({ length: Math.ceil(all.length / cols) }, (_, i) =>
    all.slice(i * cols, i * cols + cols),
  );
  return (
    <View style={styles.grid}>
      {rows.map((row) => (
        <View key={row[0].label} style={cols === 2 ? styles.gridRow : undefined}>
          {row.map((tile) => (
            <StatTile key={tile.label} grow={cols === 2} value={tile.value} label={tile.label} />
          ))}
        </View>
      ))}
    </View>
  );
}

function EventsCard({ trip }: { trip: TripDetailResponse }) {
  const { t } = useLanguage();
  return (
    <Card>
      <Text style={styles.strong} accessibilityRole="header">
        {t('events')}
      </Text>
      {trip.events.length === 0 ? <Text style={styles.caption}>{t('noEvents')}</Text> : null}
      {trip.events.map((e, idx) => (
        <View key={`${e.time}-${idx}`} style={styles.eventRow}>
          <View
            style={[
              styles.dot,
              { backgroundColor: HARSH_TYPES.includes(e.type) ? colors.coral : colors.jade },
            ]}
          />
          <View style={styles.eventText}>
            <Text style={styles.strong}>{eventLabel(t, e.type)}</Text>
            {e.peak_g ? (
              <Text style={styles.caption}>{t('peakGLine', { g: e.peak_g.toFixed(2) })}</Text>
            ) : null}
          </View>
        </View>
      ))}
    </Card>
  );
}

function DetailBody({ trip }: { trip: TripDetailResponse }) {
  const { t } = useLanguage();
  const score = trip.score == null ? null : Math.round(trip.score);
  return (
    <>
      <Card>
        <Text style={styles.eyebrow}>{t('tripScore')}</Text>
        <View style={styles.scoreRow}>
          <Text style={styles.display}>{score ?? '-'}</Text>
          {trip.tier ? <TierChip tier={trip.tier} /> : null}
        </View>
        {score !== null ? (
          <View style={styles.bar}>
            <ScoreBar value={score} thick />
          </View>
        ) : null}
      </Card>
      {trip.explanation ? (
        <Card>
          <Text style={styles.body}>{trip.explanation}</Text>
        </Card>
      ) : null}
      <TileGrid trip={trip} />
      <EventsCard trip={trip} />
    </>
  );
}

interface TripDetailProps {
  apiKey: string;
  tripId: string;
  onBack: () => void;
}

export function TripDetailScreen({ apiKey, tripId, onBack }: TripDetailProps) {
  const { language, t } = useLanguage();
  const [trip, setTrip] = useState<TripDetailResponse | null>(null);
  const [error, setError] = useState<'none' | 'notFound' | 'failed'>('none');

  const load = useCallback(async () => {
    try {
      setTrip(await getTripDetail(tripId, apiKey));
      setError('none');
    } catch (err) {
      console.warn('Could not fetch trip', err);
      setError(String(err).includes('API error 404') ? 'notFound' : 'failed');
    }
  }, [apiKey, tripId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <ScrollView style={shared.screen} contentContainerStyle={[shared.content, styles.content]}>
      <Pressable
        style={styles.back}
        onPress={onBack}
        accessibilityRole="button"
        accessibilityLabel={t('backToTrips')}
      >
        <Text style={styles.backText}>{t('backToTrips')}</Text>
      </Pressable>
      <PageHeader
        eyebrow={t('tripDetail')}
        title={trip ? formatDateTime(trip.started_at, language) : t('tripDetail')}
      />
      {error === 'notFound' ? <ErrorBanner text={t('tripNotFound')} /> : null}
      {error === 'failed' ? <ErrorBanner text={t('tripLoadError')} onRetry={load} /> : null}
      {!trip && error === 'none' ? <LoadingBlock /> : null}
      {trip ? <DetailBody trip={trip} /> : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { gap: space.lg, paddingBottom: space.xl },
  back: { minHeight: theme.minTouch, alignSelf: 'flex-start', justifyContent: 'center' },
  backText: { ...type.bodyStrong, color: colors.jadeInk },
  eyebrow: { ...type.eyebrow, color: colors.textMuted },
  display: { ...type.display, color: colors.ink },
  body: { ...type.body, color: colors.ink },
  strong: { ...type.bodyStrong, color: colors.ink },
  caption: { ...type.caption, color: colors.textMuted },
  scoreRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  bar: { marginTop: space.sm },
  grid: { gap: space.md },
  gridRow: { flexDirection: 'row', gap: space.md },
  eventRow: { flexDirection: 'row', alignItems: 'center', gap: space.md, marginTop: space.md },
  eventText: { flex: 1 },
  dot: { width: DOT, height: DOT, borderRadius: radii.pill },
});
