import { useEffect, useState } from "react";
import { api } from "../api/client.js";

let cachedEnumsPromise = null;
let cachedEnumsData = null;

let cachedConfigPromise = null;
let cachedConfigData = null;

export function fetchMetaEnums(force = false) {
  if (force) {
    cachedEnumsPromise = null;
    cachedEnumsData = null;
  }
  if (cachedEnumsData) {
    return Promise.resolve(cachedEnumsData);
  }
  if (!cachedEnumsPromise) {
    cachedEnumsPromise = api.meta
      .enums()
      .then((data) => {
        cachedEnumsData = data;
        return data;
      })
      .catch((err) => {
        cachedEnumsPromise = null;
        throw err;
      });
  }
  return cachedEnumsPromise;
}

export function fetchMetaConfig(force = false) {
  if (force) {
    cachedConfigPromise = null;
    cachedConfigData = null;
  }
  if (cachedConfigData) {
    return Promise.resolve(cachedConfigData);
  }
  if (!cachedConfigPromise) {
    cachedConfigPromise = api.meta
      .config()
      .then((data) => {
        cachedConfigData = data;
        return data;
      })
      .catch((err) => {
        cachedConfigPromise = null;
        throw err;
      });
  }
  return cachedConfigPromise;
}

export function useMetaEnums() {
  const [enums, setEnums] = useState(cachedEnumsData);
  const [loading, setLoading] = useState(!cachedEnumsData);
  const [error, setError] = useState(null);

  const load = async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMetaEnums(force);
      setEnums(data);
    } catch (err) {
      setError(err.message || "Failed to load configuration options from server.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!cachedEnumsData) {
      load();
    }
  }, []);

  return { enums, loading, error, refetch: () => load(true) };
}

export function useMetaConfig() {
  const [config, setConfig] = useState(cachedConfigData);
  const [loading, setLoading] = useState(!cachedConfigData);
  const [error, setError] = useState(null);

  const load = async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMetaConfig(force);
      setConfig(data);
    } catch (err) {
      setError(err.message || "Failed to load policy configuration from server.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!cachedConfigData) {
      load();
    }
  }, []);

  return { config, loading, error, refetch: () => load(true) };
}
