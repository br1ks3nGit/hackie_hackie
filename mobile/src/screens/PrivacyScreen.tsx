import React from 'react';
import { ScrollView, StyleSheet, Text } from 'react-native';
import { theme } from '../theme';
import { useLanguage } from '../i18n';
import { styles as shared } from '../appStyles';
import { Card, PageHeader } from '../ui';
import { LanguagePicker } from '../LanguagePicker';

// Placeholder until the Privacy step (data, reminders, delete); hosts the language picker.
export function PrivacyScreen() {
  const { t } = useLanguage();
  return (
    <ScrollView style={shared.screen} contentContainerStyle={[shared.content, styles.content]}>
      <PageHeader title={t('privacy')} />
      <Card>
        <Text style={shared.bodyStrong}>{t('language')}</Text>
        <LanguagePicker />
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { gap: theme.space.lg, paddingBottom: theme.space.xl },
});
