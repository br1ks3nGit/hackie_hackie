import { StyleSheet } from 'react-native';
import { theme } from './theme';

const { colors, radii, space, type } = theme;

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.cream },
  content: { paddingHorizontal: space.xl, paddingTop: space.md, paddingBottom: space.xxl },
  section: { marginTop: space.lg },
  flex1: { flex: 1 },
  eyebrow: { ...type.eyebrow, color: colors.textMuted },
  title: { ...type.title, color: colors.ink },
  display: { ...type.display, color: colors.ink },
  body: { ...type.body, color: colors.ink },
  bodyStrong: { ...type.bodyStrong, color: colors.ink },
  caption: { ...type.caption, color: colors.textMuted },
  explanation: { ...type.body, color: colors.textMuted, fontStyle: 'italic' },
  scoreRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  chip: { borderRadius: radii.chip, paddingHorizontal: space.sm, paddingVertical: 2 },
  switchCard: { minHeight: theme.minSwitchRow },
  switchRow: {
    minHeight: theme.minTouch,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  successStrong: { ...type.bodyStrong, color: colors.success.ink },
  successText: { ...type.body, color: colors.success.ink },
  message: { ...type.body, marginTop: space.sm, padding: space.lg, borderRadius: radii.cardSm },
  retry: { minHeight: theme.minTouch, alignSelf: 'flex-start', justifyContent: 'center' },
  warningHeader: { ...type.bodyStrong, color: colors.warning.ink, marginBottom: space.md },
  tripRow: { marginTop: space.md },
  rowGap: { flexDirection: 'row', gap: space.sm, marginTop: space.md },
  colGap: { flexDirection: 'column', gap: space.sm, marginTop: space.md },
  lastTrip: { marginBottom: space.xl },
});
