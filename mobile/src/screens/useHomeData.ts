import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AccessibilityInfo } from 'react-native';
import { useLanguage } from '../i18n';
import {
  getDriverSummary,
  getMyTrips,
  labelTrip,
  DriverSummaryResponse,
  TripListItem,
} from '../api/client';

const RELABEL_REFRESH_MS = 5000;

interface ConfirmDeps {
  apiKey: string | null;
  tripsReq: React.MutableRefObject<number>;
  setToConfirm: React.Dispatch<React.SetStateAction<TripListItem[]>>;
  refreshSummary: (key: string) => Promise<boolean>;
  refreshToConfirm: (key: string) => Promise<boolean>;
}

// Driver/passenger confirm flow: label state, announcements and the delayed re-refresh.
function useConfirmTrip(deps: ConfirmDeps) {
  const { apiKey, tripsReq, setToConfirm, refreshSummary, refreshToConfirm } = deps;
  const { t } = useLanguage();
  const tRef = useRef(t);
  tRef.current = t;
  const [labelling, setLabelling] = useState(false);
  const [labelMessage, setLabelMessage] = useState<'removed' | 'added' | null>(null);
  const [labelError, setLabelError] = useState(false);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    },
    [],
  );

  const confirmTrip = async (trip: TripListItem, tripType: 'driver' | 'passenger') => {
    if (!apiKey || labelling) return;
    setLabelling(true);
    setLabelMessage(null);
    setLabelError(false);
    try {
      const res = await labelTrip(trip.trip_id, tripType, apiKey);
      const removed = res.status === 'removed_from_score';
      setLabelMessage(removed ? 'removed' : 'added');
      AccessibilityInfo.announceForAccessibility(
        tRef.current(removed ? 'savedRemoved' : 'savedAdded'),
      );
      tripsReq.current += 1; // a list fetched before this label is stale
      setToConfirm((rows) => rows.filter((r) => r.trip_id !== trip.trip_id));
      await refreshSummary(apiKey);
      // Driver relabel reprocesses in the background; refresh again shortly
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = setTimeout(() => {
        refreshTimerRef.current = null;
        refreshSummary(apiKey);
        refreshToConfirm(apiKey);
      }, RELABEL_REFRESH_MS);
    } catch (err) {
      console.warn('Could not label trip', err);
      setLabelError(true);
      AccessibilityInfo.announceForAccessibility(tRef.current('saveError'));
    } finally {
      setLabelling(false);
    }
  };

  return { labelling, labelMessage, labelError, confirmTrip };
}

// Home data: summary, trips (recent + to confirm) and the driver/passenger confirm flow.
export function useHomeData(apiKey: string | null, active: boolean, setupFailed: boolean) {
  const [summary, setSummary] = useState<DriverSummaryResponse | null>(null);
  const [trips, setTrips] = useState<TripListItem[]>([]);
  const [toConfirm, setToConfirm] = useState<TripListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  // Request ids: only the newest response of each kind is applied
  const summaryReq = useRef(0);
  const tripsReq = useRef(0);

  const refreshSummary = useCallback(async (key: string) => {
    const id = ++summaryReq.current;
    try {
      const data = await getDriverSummary(key);
      if (id === summaryReq.current) setSummary(data);
      return true;
    } catch (err) {
      console.warn('Could not fetch summary', err);
      return false;
    }
  }, []);

  const refreshToConfirm = useCallback(async (key: string) => {
    const id = ++tripsReq.current;
    try {
      const rows = await getMyTrips(key);
      if (id === tripsReq.current) {
        setTrips(rows);
        setToConfirm(rows.filter((r) => r.needs_confirmation));
      }
      return true;
    } catch (err) {
      console.warn('Could not fetch trips to confirm', err);
      return false;
    }
  }, []);

  const refresh = useCallback(async () => {
    if (!apiKey) {
      if (setupFailed) setLoading(false);
      return;
    }
    const [okSummary, okTrips] = await Promise.all([
      refreshSummary(apiKey),
      refreshToConfirm(apiKey),
    ]);
    setLoadError(!(okSummary && okTrips));
    setLoading(false);
  }, [apiKey, setupFailed, refreshSummary, refreshToConfirm]);

  useEffect(() => {
    if (active) refresh();
  }, [active, refresh]);

  const { labelling, labelMessage, labelError, confirmTrip } = useConfirmTrip({
    apiKey,
    tripsReq,
    setToConfirm,
    refreshSummary,
    refreshToConfirm,
  });

  return {
    summary,
    trips,
    toConfirm,
    loading,
    loadError,
    labelling,
    labelMessage,
    labelError,
    refresh,
    confirmTrip,
  };
}
