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
import { theme } from './theme';

const { colors, radii, space } = theme;

interface RaisedProps {
  small?: boolean;
  bg?: string;
  style?: StyleProp<ViewStyle>;
  children?: React.ReactNode;
}

// iOS: two stacked Views, one per shadow (RN allows a single shadow per View).
// Android: elevation only.
export function Raised({ small, bg = colors.cream, style, children }: RaisedProps) {
  const radius = small ? radii.cardSm : radii.card;
  const offset = small ? 6 : 10;
  const blur = small ? 7 : 11;
  const base: ViewStyle = { borderRadius: radius, backgroundColor: bg };
  if (Platform.OS === 'android') {
    return (
      <View style={[base, styles.pad, { elevation: small ? 3 : 6 }, style]}>{children}</View>
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
          styles.pad,
          {
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

const styles = StyleSheet.create({
  pad: { padding: space.lg },
  btn: {
    minHeight: theme.minTouch,
    borderRadius: radii.cardSm,
    paddingHorizontal: space.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: { textAlign: 'center' },
  pressed: { opacity: 0.9 },
  disabled: { opacity: 0.5 },
});
