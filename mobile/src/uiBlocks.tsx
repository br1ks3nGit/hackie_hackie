import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from './theme';
import { useLanguage } from './i18n';
import { Card, CardSm, Inset, SecondaryButton } from './ui';

const { colors, radii, space, type } = theme;

const SKELETON_WIDTHS = ['70%', '100%', '45%'] as const;
const SKELETON_HEIGHT = 16;

export function TierChip({ tier }: { tier?: string | null }) {
  const { t } = useLanguage();
  const palette = (theme.colors.tier as Record<string, { soft: string; ink: string }>)[
    tier?.toUpperCase() ?? ''
  ] ?? theme.colors.tier.fallback;
  return (
    <View
      style={[styles.chip, { backgroundColor: palette.soft }]}
      accessible
      accessibilityLabel={tier ? t('tierLabel', { tier }) : undefined}
    >
      <Text style={[type.chip, { color: palette.ink }]}>{tier ?? '-'}</Text>
    </View>
  );
}

export function LoadingBlock({ live = true }: { live?: boolean }) {
  const { t } = useLanguage();
  return (
    <CardSm>
      <View
        accessible
        accessibilityLabel={t('loading')}
        accessibilityLiveRegion={live ? 'polite' : 'none'}
      >
        {SKELETON_WIDTHS.map((width) => (
          <Inset key={width} pill style={[styles.skeleton, { width }]} />
        ))}
      </View>
    </CardSm>
  );
}

interface EmptyBlockProps {
  text: string;
  hint?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyBlock({ text, hint, actionLabel, onAction }: EmptyBlockProps) {
  return (
    <Card>
      <Text style={styles.emptyText}>{text}</Text>
      {hint ? <Text style={styles.emptyText}>{hint}</Text> : null}
      {actionLabel && onAction ? (
        <SecondaryButton style={styles.action} label={actionLabel} onPress={onAction} />
      ) : null}
    </Card>
  );
}

export function ErrorBanner({ text, onRetry }: { text: string; onRetry?: () => void }) {
  const { t } = useLanguage();
  return (
    <View style={styles.banner} accessibilityRole="alert">
      <Text style={styles.bannerText}>{text}</Text>
      {onRetry ? (
        <SecondaryButton style={styles.action} label={t('retry')} onPress={onRetry} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  chip: { borderRadius: radii.chip, paddingHorizontal: space.sm, paddingVertical: 2 },
  skeleton: { minHeight: SKELETON_HEIGHT, marginVertical: space.xs },
  emptyText: { ...type.body, color: colors.textMuted, textAlign: 'center' },
  action: { marginTop: space.md, alignSelf: 'center' },
  banner: { backgroundColor: colors.danger.soft, borderRadius: radii.cardSm, padding: space.lg },
  bannerText: { ...type.bodyStrong, color: colors.danger.ink },
});
