import React from 'react';
import { Pressable, StyleSheet, Switch, Text, View, useWindowDimensions } from 'react-native';
import { theme, switchColors } from '../theme';
import { useLanguage, trendLabel, Translate } from '../i18n';
import { formatDate, formatTime } from '../format';
import { Card, CardSm, PrimaryButton, ScoreBar, SecondaryButton, StatTile } from '../ui';
import { TierChip } from '../uiBlocks';
import { DriverSummaryResponse, TripListItem } from '../api/client';

const { colors, radii, space, type } = theme;
const FONT_STACK_SCALE = 1.3;

function Chip({ text, soft, ink }: { text: string; soft: string; ink: string }) {
  return (
    <View style={[styles.chip, { backgroundColor: soft }]}>
      <Text style={[type.chip, { color: ink }]}>{text}</Text>
    </View>
  );
}

function TrendChip({ trend }: { trend: string }) {
  const { t } = useLanguage();
  const sign = trend === 'improving' ? '+' : trend === 'worsening' ? '-' : '=';
  const palette =
    trend === 'improving'
      ? colors.success
      : trend === 'worsening'
        ? colors.danger
        : colors.tier.fallback;
  return <Chip text={`${sign} ${trendLabel(t, trend)}`} soft={palette.soft} ink={palette.ink} />;
}

function Multiplier({ value }: { value: number }) {
  const { t } = useLanguage();
  const pct = Math.round(Math.abs(value - 1) * 100);
  if (pct === 0 || value === 1) return <Text style={styles.strong}>{t('noChange')}</Text>;
  const saving = value < 1;
  const palette = saving ? colors.success : colors.warning;
  return (
    <Chip
      text={t(saving ? 'savingPct' : 'surchargePct', { n: pct })}
      soft={palette.soft}
      ink={palette.ink}
    />
  );
}

export function ScoreCard({ summary }: { summary: DriverSummaryResponse | null }) {
  const { t } = useLanguage();
  const hasScore = summary !== null && summary.total_trips_90d > 0;
  const score = hasScore ? Math.round(summary.score) : null;
  return (
    <Card>
      <Text style={styles.eyebrow}>{t('last90Days')}</Text>
      <View style={styles.scoreRow}>
        <Text style={styles.display}>{score ?? '-'}</Text>
        {hasScore ? <TrendChip trend={summary.trend} /> : null}
      </View>
      {score === null ? <Text style={styles.caption}>{t('noScoreYet')}</Text> : null}
      {score !== null ? (
        <>
          <View style={styles.bar}>
            <ScoreBar value={score} thick />
          </View>
          <View style={styles.row}>
            <Text style={styles.caption}>{t('poor')}</Text>
            <Text style={styles.caption}>{t('excellent')}</Text>
          </View>
        </>
      ) : null}
      {hasScore ? (
        <>
          <View style={styles.divider} />
          <View style={styles.row}>
            <Text style={styles.body}>{t('premiumEffect')}</Text>
            <Multiplier value={summary.premium_multiplier} />
          </View>
        </>
      ) : null}
    </Card>
  );
}

export function StatRow({ summary }: { summary: DriverSummaryResponse | null }) {
  const { t } = useLanguage();
  const { fontScale } = useWindowDimensions();
  const grow = fontScale <= FONT_STACK_SCALE;
  return (
    <View style={grow ? styles.tiles : styles.tilesCol}>
      <StatTile grow={grow} value={summary?.total_trips_90d ?? 0} label={t('statTrips')} />
      <StatTile
        grow={grow}
        value={(summary?.total_distance_km_90d ?? 0).toFixed(1)}
        label={t('statKm')}
      />
      <StatTile
        grow={grow}
        value={summary?.tier ?? '-'}
        label={t('statTier')}
        node={summary?.tier ? <TierChip tier={summary.tier} /> : undefined}
      />
    </View>
  );
}

interface RecordingCardProps {
  recording: boolean;
  inTrip: boolean;
  drivingMode: boolean;
  chunkCount: number;
  tripId: string | null;
  onToggleRecording: () => void;
  onDrivingMode: (value: boolean) => void;
}

function RecordingPanel(props: RecordingCardProps) {
  const { t } = useLanguage();
  return (
    <View style={styles.recBanner}>
      <Text style={styles.recStrong}>{t('recordingNow')}</Text>
      <Text style={styles.recText}>
        {t('statusLine', { value: t(props.inTrip ? 'statusInTrip' : 'statusIdle') })}
      </Text>
      <Text style={styles.recText}>
        {t('drivingLine', { value: t(props.drivingMode ? 'yes' : 'no') })}
      </Text>
      <Text style={styles.recText}>{t('chunksUploaded', { count: props.chunkCount })}</Text>
      {props.tripId ? (
        <Text style={styles.recText}>{t('tripIdLine', { id: props.tripId.substring(0, 16) })}</Text>
      ) : null}
    </View>
  );
}

export function RecordingCard(props: RecordingCardProps) {
  const { t } = useLanguage();
  return (
    <Card>
      <Pressable
        style={styles.switchRow}
        onPress={() => props.onDrivingMode(!props.drivingMode)}
        accessibilityRole="switch"
        accessibilityState={{ checked: props.drivingMode }}
        accessibilityLabel={t('drivingModeLabel')}
      >
        <Text style={styles.strong}>
          {t('drivingModeState', { state: t(props.drivingMode ? 'on' : 'off') })}
        </Text>
        <SwitchView value={props.drivingMode} onChange={props.onDrivingMode} />
      </Pressable>
      <Text style={styles.caption}>{t('drivingModeHint')}</Text>
      <PrimaryButton
        style={styles.gapTop}
        danger={props.recording}
        label={t(props.recording ? 'stopRecording' : 'startRecording')}
        onPress={props.onToggleRecording}
      />
      {props.recording ? <RecordingPanel {...props} /> : null}
    </Card>
  );
}

function SwitchView({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <Switch
      value={value}
      onValueChange={onChange}
      accessible={false}
      trackColor={{ true: switchColors.on, false: switchColors.off }}
      thumbColor={switchColors.thumb}
    />
  );
}

interface ConfirmCardProps {
  trips: TripListItem[];
  labelling: boolean;
  onConfirm: (trip: TripListItem, type: 'driver' | 'passenger') => void;
}

function ConfirmRow({ trip, labelling, onConfirm }: Omit<ConfirmCardProps, 'trips'> & { trip: TripListItem }) {
  const { language, t } = useLanguage();
  const { fontScale } = useWindowDimensions();
  const stacked = fontScale > FONT_STACK_SCALE;
  // flex: 1 only in a row: in a stacked column it would collapse the buttons to min height
  const btnFlex = stacked ? undefined : styles.flex1;
  const date = formatDate(trip.started_at, language);
  const time = formatTime(trip.started_at, language);
  return (
    <CardSm style={styles.gapTop}>
      <Text style={styles.strong}>
        {date} {time}
        {'\n'}
        {t('kmValue', { km: trip.distance_km.toFixed(1) })}
      </Text>
      <View style={stacked ? styles.colGap : styles.rowGap}>
        <PrimaryButton
          style={btnFlex}
          label={t('iWasDriving')}
          disabled={labelling}
          onPress={() => onConfirm(trip, 'driver')}
          accessibilityLabel={t('iWasDrivingA11y', { date, time })}
          accessibilityState={{ disabled: labelling }}
        />
        <SecondaryButton
          style={btnFlex}
          label={t('iWasPassenger')}
          disabled={labelling}
          onPress={() => onConfirm(trip, 'passenger')}
          accessibilityLabel={t('iWasPassengerA11y', { date, time })}
          accessibilityState={{ disabled: labelling }}
        />
      </View>
    </CardSm>
  );
}

export function ConfirmCard({ trips, labelling, onConfirm }: ConfirmCardProps) {
  const { t } = useLanguage();
  return (
    <Card bg={colors.warning.soft}>
      <Text style={styles.warningHeader} accessibilityRole="header">
        {t('tripsToConfirm')}
      </Text>
      {trips.map((trip) => (
        <ConfirmRow key={trip.trip_id} trip={trip} labelling={labelling} onConfirm={onConfirm} />
      ))}
    </Card>
  );
}

export function messageFor(
  t: Translate,
  state: { labelError: boolean; labelMessage: 'removed' | 'added' | null },
): string {
  if (state.labelError) return t('saveError');
  if (state.labelMessage === 'removed') return t('savedRemoved');
  if (state.labelMessage === 'added') return t('savedAdded');
  return '';
}

const styles = StyleSheet.create({
  eyebrow: { ...type.eyebrow, color: colors.textMuted },
  display: { ...type.display, color: colors.ink },
  body: { ...type.body, color: colors.ink },
  strong: { ...type.bodyStrong, color: colors.ink },
  caption: { ...type.caption, color: colors.textMuted },
  scoreRow: { flexDirection: 'row', alignItems: 'center', gap: space.md, flexWrap: 'wrap' },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: space.sm },
  bar: { marginTop: space.sm },
  divider: { height: 1, backgroundColor: colors.mist, marginVertical: space.md },
  chip: { borderRadius: radii.chip, paddingHorizontal: space.sm, paddingVertical: 2 },
  tiles: { flexDirection: 'row', gap: space.md },
  tilesCol: { flexDirection: 'column', gap: space.md },
  switchRow: {
    minHeight: theme.minSwitchRow,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  gapTop: { marginTop: space.md },
  flex1: { flex: 1 },
  rowGap: { flexDirection: 'row', gap: space.sm, marginTop: space.md },
  colGap: { flexDirection: 'column', gap: space.sm, marginTop: space.md },
  warningHeader: { ...type.bodyStrong, color: colors.warning.ink, marginBottom: space.xs },
  recBanner: {
    marginTop: space.md,
    padding: space.lg,
    borderRadius: radii.cardSm,
    backgroundColor: colors.danger.soft,
  },
  recStrong: { ...type.bodyStrong, color: colors.danger.ink },
  recText: { ...type.body, color: colors.danger.ink },
});
