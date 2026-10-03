import React, { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  findNodeHandle,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import { theme } from '../theme';
import { useLanguage, TranslationKey } from '../i18n';
import { styles as shared } from '../appStyles';
import { Card, PageHeader, PrimaryButton, SecondaryButton } from '../ui';
import { Checkbox, ErrorBanner, StepDots } from '../uiBlocks';

const { space, type, colors } = theme;
const STACK_FONT_SCALE = 1.3;

const STEPS: { title: TranslationKey; body: TranslationKey }[] = [
  { title: 'onboarding1Title', body: 'onboarding1Body' },
  { title: 'onboarding2Title', body: 'onboarding2Body' },
  { title: 'onboarding3Title', body: 'onboarding3Body' },
  { title: 'onboarding4Title', body: 'onboarding4Body' },
];

interface Props {
  onComplete: () => Promise<void>;
}

export function OnboardingScreen({ onComplete }: Props) {
  const { t } = useLanguage();
  const [index, setIndex] = useState(0);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const titleRef = useRef<Text>(null);
  const first = useRef(true);
  const inFlight = useRef(false);
  const { fontScale } = useWindowDimensions();
  const stacked = fontScale > STACK_FONT_SCALE;
  const last = index === STEPS.length - 1;
  const blocked = busy || (last && !agreed);
  const step = STEPS[index];
  const title = t(step.title);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const node = findNodeHandle(titleRef.current);
    if (node) AccessibilityInfo.setAccessibilityFocus(node);
  }, [index, title]);

  const finish = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(false);
    try {
      await onComplete();
    } catch {
      setError(true);
      setBusy(false);
      inFlight.current = false;
    }
  };

  return (
    <ScrollView style={shared.screen} contentContainerStyle={[shared.content, styles.content]}>
      <PageHeader
        eyebrow={t('stepOf', { n: index + 1, total: STEPS.length })}
        title={title}
        titleRef={titleRef}
      />
      <Card>
        <Text style={styles.body}>{t(step.body)}</Text>
      </Card>
      <View style={styles.dots}>
        <StepDots count={STEPS.length} index={index} />
      </View>
      {last ? (
        <Card>
          <Text style={styles.body}>{t('consentData')}</Text>
          <Checkbox disabled={busy} checked={agreed} onChange={setAgreed} label={t('consent')} />
        </Card>
      ) : null}
      {error ? <ErrorBanner text={t('setupFailed')} onRetry={finish} /> : null}
      <View style={stacked ? styles.footerCol : styles.footer}>
        <PrimaryButton
          style={stacked ? undefined : styles.next}
          label={busy ? t('starting') : t(last ? 'firstTrip' : 'continue')}
          disabled={blocked}
          accessibilityState={{ disabled: blocked, busy }}
          accessibilityHint={last && !agreed ? t('consent') : undefined}
          onPress={last ? finish : () => setIndex(index + 1)}
        />
        {index > 0 ? (
          <SecondaryButton
            label={t('back')}
            disabled={busy}
            onPress={() => setIndex(index - 1)}
          />
        ) : null}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { gap: space.lg, paddingBottom: space.xl },
  body: { ...type.body, color: colors.ink },
  dots: { alignItems: 'center' },
  footer: { flexDirection: 'row-reverse', gap: space.md, alignItems: 'center' },
  footerCol: { flexDirection: 'column', gap: space.md },
  next: { flex: 1 },
});
