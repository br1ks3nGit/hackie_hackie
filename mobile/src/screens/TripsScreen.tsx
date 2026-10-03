import React, { useCallback, useEffect, useRef, useState } from 'react';
import { BackHandler, RefreshControl, ScrollView, StyleSheet } from 'react-native';
import { theme } from '../theme';
import { useLanguage } from '../i18n';
import { styles as shared } from '../appStyles';
import { PageHeader } from '../ui';
import { EmptyBlock, ErrorBanner, LoadingBlock } from '../uiBlocks';
import { getMyTrips, TripListItem } from '../api/client';
import { TripRow } from './TripRow';
import { TripDetailScreen } from './TripDetailScreen';

const TRIPS_LIMIT = 50;
const SKELETON_ROWS = 3;

interface TripsScreenProps {
  apiKey: string | null;
  selectedId: string | null;
  onSelect: (tripId: string | null) => void;
  refreshKey: number;
  setupFailed: boolean;
  onRetrySetup: () => void;
}

export function TripsScreen(props: TripsScreenProps) {
  const { apiKey, selectedId, onSelect, refreshKey, setupFailed, onRetrySetup } = props;
  const { t } = useLanguage();
  const [trips, setTrips] = useState<TripListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);

  const reqRef = useRef(0);

  const load = useCallback(async () => {
    if (!apiKey) {
      if (setupFailed) setLoading(false);
      return;
    }
    const id = ++reqRef.current;
    try {
      const rows = await getMyTrips(apiKey, TRIPS_LIMIT);
      if (id !== reqRef.current) return; // a newer request superseded this one
      setTrips(rows);
      setError(false);
    } catch (err) {
      console.warn('Could not fetch trips', err);
      if (id === reqRef.current) setError(true);
    } finally {
      if (id === reqRef.current) setLoading(false);
    }
  }, [apiKey, setupFailed]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  useEffect(() => {
    if (!selectedId) return undefined;
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      onSelect(null);
      return true;
    });
    return () => sub.remove();
  }, [selectedId, onSelect]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  if (selectedId && apiKey) {
    return <TripDetailScreen apiKey={apiKey} tripId={selectedId} onBack={() => onSelect(null)} />;
  }

  return (
    <ScrollView
      style={shared.screen}
      contentContainerStyle={[shared.content, styles.body]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      <PageHeader title={t('trips')} />
      {setupFailed && !apiKey ? (
        <ErrorBanner text={t('setupFailed')} onRetry={onRetrySetup} />
      ) : null}
      {error ? <ErrorBanner text={t('tripsLoadError')} onRetry={load} /> : null}
      {loading
        ? Array.from({ length: SKELETON_ROWS }, (_, i) => <LoadingBlock key={i} live={i === 0} />)
        : null}
      {!loading && !error && !setupFailed && trips.length === 0 ? (
        <EmptyBlock text={t('noTrips')} hint={t('noTripsHint')} />
      ) : null}
      {trips.map((trip) => (
        <TripRow key={trip.trip_id} trip={trip} onPress={() => onSelect(trip.trip_id)} />
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  body: { gap: theme.space.md, paddingBottom: theme.space.xl },
});
