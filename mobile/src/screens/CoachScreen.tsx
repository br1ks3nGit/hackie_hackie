import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { theme } from '../theme';
import { useLanguage, TranslationKey } from '../i18n';
import { styles as shared } from '../appStyles';
import { Card, PageHeader } from '../ui';

const { colors, radii, space, type } = theme;
const BADGE = 40;

const TIPS: { n: number; title: TranslationKey; body: TranslationKey }[] = [
  { n: 1, title: 'tip1Title', body: 'tip1Body' },
  { n: 2, title: 'tip2Title', body: 'tip2Body' },
  { n: 3, title: 'tip3Title', body: 'tip3Body' },
  { n: 4, title: 'tip4Title', body: 'tip4Body' },
];

export function CoachScreen() {
  const { t } = useLanguage();
  return (
    <ScrollView style={shared.screen} contentContainerStyle={[shared.content, styles.content]}>
      <PageHeader title={t('coach')} />
      {TIPS.map((tip) => (
        <Card key={tip.n}>
          <View style={styles.row}>
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{tip.n}</Text>
            </View>
            <View style={styles.text}>
              <Text style={styles.title}>{t(tip.title)}</Text>
              <Text style={styles.body}>{t(tip.body)}</Text>
            </View>
          </View>
        </Card>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { gap: space.lg, paddingBottom: space.xl },
  row: { flexDirection: 'row', gap: space.md, alignItems: 'flex-start' },
  badge: {
    width: BADGE,
    height: BADGE,
    borderRadius: radii.chip,
    backgroundColor: colors.success.soft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: { ...type.bodyStrong, color: colors.success.ink },
  text: { flex: 1 },
  title: { ...type.bodyStrong, color: colors.ink },
  body: { ...type.caption, color: colors.textMuted },
});
