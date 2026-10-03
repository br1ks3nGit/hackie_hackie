import React from 'react';
import {
  Platform,
  Pressable,
  PressableProps,
  StyleProp,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { theme } from './theme';
import { useLanguage } from './i18n';

const { colors, radii, space } = theme;

interface RaisedProps {
  small?: boolean;
  bg?: string;
  pad?: number;
  style?: StyleProp<ViewStyle>;
  children?: React.ReactNode;
}

// iOS: two stacked Views, one per shadow (RN allows a single shadow per View).
// Android: elevation only.
export function Raised({ small, bg = colors.cream, pad = space.lg, style, children }: RaisedProps) {
  const radius = small ? radii.cardSm : radii.card;
  const offset = small ? 6 : 10;
  const blur = small ? 7 : 11;
  const base: ViewStyle = { borderRadius: radius, backgroundColor: bg };
  if (Platform.OS === 'android') {
    return (
      <View style={[base, { padding: pad, elevation: small ? 3 : 6 }, style]}>{children}</View>
    );
  }
  return (
    <View
      style={[
        base,
        {
          shadowColor: colors.neuDark,
          shadowOffset: { width: offset, height: offset },
          shadowRadius: blur,
          shadowOpacity: 1,
        },
        style,
      ]}
    >
      <View
        style={[
          base,
          {
            padding: pad,
            shadowColor: colors.neuLight,
            shadowOffset: { width: -offset, height: -offset },
            shadowRadius: blur,
            shadowOpacity: 1,
          },
        ]}
      >
        {children}
      </View>
    </View>
  );
}

export const Card = (props: Omit<RaisedProps, 'small'>) => <Raised {...props} />;
export const CardSm = (props: Omit<RaisedProps, 'small'>) => <Raised {...props} small />;

interface ButtonProps extends Omit<PressableProps, 'style' | 'children'> {
  label: string;
  danger?: boolean;
  style?: StyleProp<ViewStyle>;
}

export function PrimaryButton({ label, danger, disabled, style, ...rest }: ButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      {...rest}
      disabled={disabled}
      style={({ pressed }) => [
        styles.btn,
        {
          backgroundColor: danger
            ? pressed
              ? colors.dangerPressed
              : colors.dangerSolid
            : colors.jade,
        },
        pressed && styles.pressed,
        disabled && styles.disabled,
        style,
      ]}
    >
      <Text
        style={[
          theme.type.bodyStrong,
          styles.label,
          { color: danger ? colors.white : colors.onJade },
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export function SecondaryButton({ label, disabled, style, ...rest }: ButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      {...rest}
      disabled={disabled}
      style={({ pressed }) => [
        styles.btn,
        { backgroundColor: colors.cream },
        pressed && styles.pressed,
        pressed && { backgroundColor: colors.trough },
        disabled && styles.disabled,
        style,
      ]}
    >
      <Text style={[theme.type.bodyStrong, styles.label, { color: colors.jadeInk }]}>{label}</Text>
    </Pressable>
  );
}

interface InsetProps {
  pill?: boolean;
  style?: StyleProp<ViewStyle>;
  children?: React.ReactNode;
}

// Trough per design-system 8.3: no RN inset shadow, so tinted fill plus opposed borders.
export function Inset({ pill, style, children }: InsetProps) {
  return (
    <View style={[styles.inset, { borderRadius: pill ? radii.pill : radii.chip }, style]}>
      {children}
    </View>
  );
}

const BAR_THICK = 12;
const BAR_THIN = 8;
const GOOD_SCORE = 80;

export function ScoreBar({ value, thick }: { value: number; thick?: boolean }) {
  const { t } = useLanguage();
  const now = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <Inset
      pill
      style={[styles.barTrack, { minHeight: thick ? BAR_THICK : BAR_THIN }]}
    >
      <View
        accessible
        accessibilityRole="progressbar"
        accessibilityLabel={t('scoreLabel')}
        accessibilityValue={{ min: 0, max: 100, now }}
        style={styles.barHit}
      >
        <View
          style={[
            styles.barFill,
            { width: `${now}%`, backgroundColor: now >= GOOD_SCORE ? colors.jade : colors.coral },
          ]}
        />
      </View>
    </Inset>
  );
}

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  right?: React.ReactNode;
  titleRef?: React.Ref<Text>;
}

export function PageHeader({ eyebrow, title, right, titleRef }: PageHeaderProps) {
  return (
    <View style={styles.header}>
      <View style={styles.headerText}>
        {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
        <Text ref={titleRef} style={styles.title} accessibilityRole="header">
          {title}
        </Text>
      </View>
      {right}
    </View>
  );
}

interface StatTileProps {
  value: string | number;
  label: string;
  // Rendered instead of the text value (e.g. tier chip); `value` still feeds the a11y label
  node?: React.ReactNode;
  grow?: boolean;
}

export function StatTile({ value, label, node, grow = true }: StatTileProps) {
  return (
    <CardSm pad={space.md} style={grow ? styles.tile : styles.tileCol}>
      <View style={styles.tileBody} accessible accessibilityLabel={`${label}: ${value}`}>
        {node ?? <Text style={styles.tileValue}>{value}</Text>}
        <Text style={styles.tileLabel}>{label}</Text>
      </View>
    </CardSm>
  );
}

interface Tab<K extends string> {
  key: K;
  label: string;
}

interface BottomTabBarProps<K extends string> {
  tabs: Tab<K>[];
  active: K;
  onChange: (key: K) => void;
}

export function BottomTabBar<K extends string>({ tabs, active, onChange }: BottomTabBarProps<K>) {
  const insets = useSafeAreaInsets();
  return (
    <View
      accessibilityRole="tablist"
      style={[styles.tabBar, { paddingBottom: insets.bottom }]}
    >
      {tabs.map((tab) => {
        const selected = tab.key === active;
        return (
          <Pressable
            key={tab.key}
            style={styles.tab}
            onPress={() => onChange(tab.key)}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            accessibilityLabel={tab.label}
          >
            {selected ? (
              <Inset pill style={styles.tabPill}>
                <Text style={styles.tabLabelOn}>{tab.label}</Text>
              </Inset>
            ) : (
              <View style={styles.tabPill}>
                <Text style={styles.tabLabel}>{tab.label}</Text>
              </View>
            )}
          </Pressable>
        );
      })}
    </View>
  );
}

const { type } = theme;

const styles = StyleSheet.create({
  eyebrow: { ...type.eyebrow, color: colors.textMuted },
  title: { ...type.title, color: colors.ink },
  inset: {
    backgroundColor: colors.trough,
    borderTopWidth: 1,
    borderLeftWidth: 1,
    borderTopColor: colors.neuDark,
    borderLeftColor: colors.neuDark,
    borderBottomWidth: 1,
    borderRightWidth: 1,
    borderBottomColor: colors.neuLight,
    borderRightColor: colors.neuLight,
  },
  barTrack: { flexDirection: 'row', overflow: 'hidden' },
  barHit: { flex: 1, flexDirection: 'row' },
  barFill: { alignSelf: 'stretch', borderRadius: radii.pill },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  headerText: { flex: 1 },
  tile: { flex: 1, minWidth: 0 },
  tileCol: { alignSelf: 'stretch' },
  tileBody: { alignItems: 'center' },
  tileValue: { ...type.bodyStrong, color: colors.ink, textAlign: 'center' },
  tileLabel: { ...type.chip, fontWeight: '500', color: colors.textMuted, textAlign: 'center' },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: colors.cream,
    borderTopWidth: 1,
    borderTopColor: colors.neuDark,
  },
  tab: { flex: 1, minHeight: 56, alignItems: 'center', justifyContent: 'center' },
  tabPill: { paddingHorizontal: space.md, paddingVertical: space.sm },
  tabLabel: { ...type.chip, fontWeight: '500', color: colors.textMuted },
  tabLabelOn: { ...type.chip, color: colors.jadeInk },
  btn: {
    minHeight: theme.minTouch,
    borderRadius: radii.cardSm,
    paddingHorizontal: space.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: { textAlign: 'center' },
  pressed: { opacity: 0.9 },
  disabled: { opacity: theme.disabledOpacity },
});
