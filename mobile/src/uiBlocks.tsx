import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { theme } from './theme';
import { useLanguage } from './i18n';
import { checkConnection, useOnline } from './connectivity';
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

// The live-region wrapper stays mounted so the offline text is announced once when it appears.
export function OfflineBanner() {
  const { t } = useLanguage();
  const online = useOnline();
  const [checking, setChecking] = useState(false);
  const retry = async () => {
    setChecking(true);
    await checkConnection();
    setChecking(false);
  };
  return (
    <View accessibilityLiveRegion="polite">
      {online ? null : (
        <View style={styles.offline}>
          <Text style={styles.offlineText}>{t('offlineBanner')}</Text>
          <SecondaryButton
            label={t('retry')}
            onPress={retry}
            disabled={checking}
          />
        </View>
      )}
    </View>
  );
}

const BOX = 24;
const DOT = 10;
const DOT_WIDE = 24;

interface CheckboxProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}

export function Checkbox({ checked, onChange, label, disabled }: CheckboxProps) {
  return (
    <Pressable
      style={[styles.checkRow, disabled && styles.checkDisabled]}
      onPress={() => onChange(!checked)}
      disabled={disabled}
      accessibilityRole="checkbox"
      accessibilityState={{ checked, disabled: !!disabled }}
      accessibilityLabel={label}
    >
      {checked ? (
        <View style={[styles.box, styles.boxOn]}>
          <Text style={styles.check} maxFontSizeMultiplier={1}>{'\u2713'}</Text>
        </View>
      ) : (
        <Inset style={[styles.box, styles.boxOff]} />
      )}
      <Text style={styles.checkLabel}>{label}</Text>
    </Pressable>
  );
}

// Decorative: the "Step n of N" eyebrow is the spoken text.
export function StepDots({ count, index }: { count: number; index: number }) {
  return (
    <View
      style={styles.dots}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    >
      {Array.from({ length: count }, (_, i) => (
        <View key={i} style={[styles.dot, i === index && styles.dotOn]} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  checkRow: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: space.md },
  checkDisabled: { opacity: theme.disabledOpacity },
  box: { width: BOX, height: BOX, borderRadius: radii.chip },
  boxOff: {
    borderTopWidth: 2,
    borderLeftWidth: 2,
    borderBottomWidth: 2,
    borderRightWidth: 2,
    borderTopColor: colors.controlOff,
    borderLeftColor: colors.controlOff,
    borderBottomColor: colors.controlOff,
    borderRightColor: colors.controlOff,
  },
  boxOn: { backgroundColor: colors.jadeDeep, alignItems: 'center', justifyContent: 'center' },
  check: { ...type.bodyStrong, color: colors.white },
  checkLabel: { ...type.body, color: colors.ink, flex: 1 },
  dots: { flexDirection: 'row', gap: space.sm, alignItems: 'center' },
  dot: { width: DOT, height: DOT, borderRadius: radii.pill, backgroundColor: colors.mist },
  dotOn: { width: DOT_WIDE, backgroundColor: colors.jadeDeep },
  chip: { borderRadius: radii.chip, paddingHorizontal: space.sm, paddingVertical: 2 },
  skeleton: { minHeight: SKELETON_HEIGHT, marginVertical: space.xs },
  emptyText: { ...type.body, color: colors.textMuted, textAlign: 'center' },
  action: { marginTop: space.md, alignSelf: 'center' },
  banner: { backgroundColor: colors.danger.soft, borderRadius: radii.cardSm, padding: space.lg },
  offline: {
    minHeight: 44,
    backgroundColor: colors.warning.soft,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
  },
  offlineText: { ...type.bodyStrong, color: colors.warning.ink, flex: 1 },
  bannerText: { ...type.bodyStrong, color: colors.danger.ink },
});
