import React, { createContext, useContext, useEffect, useState } from "react";
import { api, getStoredToken, setStoredToken } from "../api/client.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => getStoredToken());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadUser() {
      const activeToken = getStoredToken();
      if (!activeToken) {
        setLoading(false);
        return;
      }
      try {
        const userData = await api.auth.me();
        setUser(userData);
      } catch (err) {
        setStoredToken(null);
        setToken(null);
        setUser(null);
      } finally {
        setLoading(false);
      }
    }
    loadUser();
  }, []);

  async function login(email, password) {
    setError(null);
    const data = await api.auth.login({ email, password });
    setStoredToken(data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  }

  async function register(name, email, password) {
    setError(null);
    const createdUser = await api.auth.register({ name, email, password });
    const loginData = await api.auth.login({ email, password });
    setStoredToken(loginData.access_token);
    setToken(loginData.access_token);
    setUser(loginData.user);
    return loginData.user;
  }

  async function logout() {
    try {
      await api.auth.logout();
    } finally {
      setStoredToken(null);
      setToken(null);
      setUser(null);
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        loading,
        error,
        setError,
        login,
        register,
        logout,
        isAuthenticated: Boolean(user),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
