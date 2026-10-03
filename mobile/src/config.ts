const DEFAULT_API_BASE_URL = 'http://localhost:8000';

// Backend origin without trailing slash or /v1. Override with EXPO_PUBLIC_API_BASE_URL.
export const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL).replace(
  /\/+$/,
  '',
);
