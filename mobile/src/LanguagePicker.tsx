import React from 'react';
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { theme } from './theme';
import { Language, useLanguage } from './i18n';

const STACK_FONT_SCALE = 1.3;
const PILL_MIN_WIDTH = 96;

const OPTIONS: { code: Language; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'zh-CN', label: '普通话 · 简体' },
  { code: 'zh-HK', label: '廣東話 · 繁體' },
];

export function LanguagePicker() {
  const { language, setLanguage, t } = useLanguage();
  const { fontScale } = useWindowDimensions();
  const stacked = fontScale > STACK_FONT_SCALE;
  return (
    <View
      style={[styles.group, stacked && styles.groupStacked]}
      accessibilityRole="radiogroup"
      accessibilityLabel={t('language')}
    >
      {OPTIONS.map(({ code, label }) => {
        const selected = code === language;
        return (
          <Pressable
            key={code}
            style={({ pressed }) => [
              styles.pill,
              selected ? styles.pillSelected : styles.pillUnselected,
              pressed && styles.pressed,
            ]}
            onPress={() => setLanguage(code)}
            accessibilityRole="radio"
            accessibilityState={{ selected, checked: selected }}
            accessibilityLanguage={code}
          >
            <Text style={[styles.label, selected && styles.labelSelected]}>{label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const { colors, radii, space, type } = theme;

const styles = StyleSheet.create({
  group: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.md },
  groupStacked: { flexDirection: 'column', flexWrap: 'nowrap' },
  pill: {
    flexGrow: 1,
    flexBasis: 'auto',
    minWidth: PILL_MIN_WIDTH,
    minHeight: theme.minTouch,
    borderRadius: radii.pill,
    paddingHorizontal: space.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
  },
  pillUnselected: { borderColor: colors.controlOff },
  pillSelected: {
    backgroundColor: colors.trough,
    borderTopColor: colors.neuDark,
    borderLeftColor: colors.neuDark,
    borderBottomColor: colors.neuLight,
    borderRightColor: colors.neuLight,
  },
  pressed: { opacity: 0.9 },
  label: { ...type.caption, color: colors.ink, textAlign: 'center' },
  labelSelected: { ...type.bodyStrong, fontSize: type.caption.fontSize, color: colors.jadeInk },
});
