import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { theme } from '../theme';
import { useLanguage } from '../i18n';
import { formatDateTime } from '../format';
import { CardSm, ScoreBar } from '../ui';
import { TierChip } from '../uiBlocks';
import { TripListItem } from '../api/client';

const { colors, space, type } = theme;

export function TripRow({ trip, onPress }: { trip: TripListItem; onPress: () => void }) {
  const { language, t } = useLanguage();
  const when = formatDateTime(trip.started_at, language);
  const km = trip.distance_km.toFixed(1);
  const label =
    trip.score === null
      ? t('tripA11yNoScore', { date: when, km })
      : t('tripA11y', { date: when, km, score: Math.round(trip.score), tier: trip.tier ?? '-' });
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => (pressed ? styles.pressed : undefined)}
    >
      <CardSm>
        <View style={styles.row}>
          <Text style={styles.strong}>{when}</Text>
          <Text style={styles.strong}>{trip.score === null ? '-' : Math.round(trip.score)}</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.caption}>{t('kmValue', { km })}</Text>
          {trip.tier ? <TierChip tier={trip.tier} /> : null}
        </View>
        {trip.score !== null ? (
          <View style={styles.bar}>
            <ScoreBar value={trip.score} />
          </View>
        ) : null}
      </CardSm>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: space.sm },
  strong: { ...type.bodyStrong, color: colors.ink },
  caption: { ...type.caption, color: colors.textMuted },
  pressed: { opacity: 0.9 },
  bar: { marginTop: space.sm },
});
