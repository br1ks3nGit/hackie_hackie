import React, { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  InteractionManager,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
  findNodeHandle,
} from 'react-native';
import { theme } from './theme';
import { useLanguage } from './i18n';
import { Card } from './ui';
import { LANGUAGE_OPTIONS, LanguagePicker } from './LanguagePicker';

function focusNode(ref: React.RefObject<View | Text | null>) {
  const node = findNodeHandle(ref.current);
  if (node) AccessibilityInfo.setAccessibilityFocus(node);
}

export function AppHeader() {
  const { language, t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [panelTop, setPanelTop] = useState<number>(theme.minTouch + theme.space.sm);
  const titleRef = useRef<Text>(null);
  const buttonRef = useRef<View>(null);
  const wasOpen = useRef(false);
  const current = LANGUAGE_OPTIONS.find((o) => o.code === language) ?? LANGUAGE_OPTIONS[0];

  useEffect(() => {
    if (open) {
      wasOpen.current = true;
      const task = InteractionManager.runAfterInteractions(() => focusNode(titleRef));
      return () => task.cancel();
    }
    // iOS returns focus through Modal onDismiss; Android has no such callback.
    if (wasOpen.current && Platform.OS === 'android') focusNode(buttonRef);
    wasOpen.current = false;
    return undefined;
  }, [open]);

  return (
    <View
      style={styles.bar}
      onLayout={(e) => setPanelTop(e.nativeEvent.layout.y + e.nativeEvent.layout.height + space.sm)}
    >
      <Text style={styles.mark} importantForAccessibility="no" accessibilityElementsHidden>
        BT
      </Text>
      <Pressable
        ref={buttonRef}
        style={({ pressed }) => [styles.button, pressed ? styles.buttonPressed : styles.buttonRest]}
        onPress={() => setOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={`${t('language')}: ${current.label}`}
        accessibilityHint={t('languageHint')}
      >
        <Text style={styles.short} importantForAccessibility="no">
          {current.short}
        </Text>
      </Pressable>
      <Modal
        transparent
        statusBarTranslucent
        animationType="fade"
        visible={open}
        supportedOrientations={['portrait', 'landscape']}
        onRequestClose={() => setOpen(false)}
        onDismiss={() => focusNode(buttonRef)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setOpen(false)}
          accessibilityElementsHidden
          importantForAccessibility="no"
        />
        <View
          style={[styles.panel, { top: panelTop }]}
          accessibilityViewIsModal
          onAccessibilityEscape={() => setOpen(false)}
        >
          <Card>
            <Text ref={titleRef} style={styles.panelTitle} accessibilityRole="header">
              {t('language')}
            </Text>
            <LanguagePicker onSelect={() => setOpen(false)} />
          </Card>
        </View>
      </Modal>
    </View>
  );
}

const { colors, radii, space, type } = theme;

const styles = StyleSheet.create({
  bar: {
    minHeight: theme.minTouch,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
  },
  mark: { ...type.bodyStrong, color: colors.jadeInk },
  button: {
    minHeight: theme.minTouch,
    minWidth: theme.minTouch,
    paddingHorizontal: space.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.pill,
    borderWidth: 1,
  },
  buttonRest: { borderColor: colors.controlOff },
  buttonPressed: {
    opacity: 0.9,
    backgroundColor: colors.trough,
    borderTopColor: colors.neuDark,
    borderLeftColor: colors.neuDark,
    borderBottomColor: colors.neuLight,
    borderRightColor: colors.neuLight,
  },
  short: { ...type.bodyStrong, color: colors.jadeInk },
  backdrop: { ...StyleSheet.absoluteFillObject },
  panel: { position: 'absolute', left: space.lg, right: space.lg },
  panelTitle: { ...type.bodyStrong, color: colors.ink },
});
