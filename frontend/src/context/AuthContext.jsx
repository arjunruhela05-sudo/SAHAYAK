import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

const USERS_KEY = "sahayak_users_v2";
const SESSION_KEY = "sahayak_session_v2";

const seedUsers = [
  { id: "admin-1", name: "System Admin", email: "admin@sahayak.local", phone: "", password: "Admin@123", role: "admin", status: "Active", createdAt: new Date().toISOString() },
  { id: "authority-1", name: "Response Authority", email: "authority@sahayak.local", phone: "", password: "Authority@123", role: "authority", status: "Active", createdAt: new Date().toISOString() },
];

const read = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [users, setUsers] = useState(() => read(USERS_KEY, seedUsers));
  const [user, setUser] = useState(() => read(SESSION_KEY, null));

  useEffect(() => localStorage.setItem(USERS_KEY, JSON.stringify(users)), [users]);
  useEffect(() => {
    if (user) localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    else localStorage.removeItem(SESSION_KEY);
  }, [user]);

  const register = (payload) => {
    const email = payload.email.trim().toLowerCase();
    if (users.some(u => u.email === email)) throw new Error("An account with this email already exists.");
    const created = { ...payload, id: crypto.randomUUID(), email, status: "Active", createdAt: new Date().toISOString() };
    setUsers(prev => [...prev, created]);
    const session = { ...created };
    delete session.password;
    setUser(session);
    return session;
  };

  const login = (email, password, role) => {
    const found = users.find(u => u.email === email.trim().toLowerCase() && u.password === password && (!role || u.role === role));
    if (!found) throw new Error("Invalid email, password, or role.");
    if (found.status !== "Active") throw new Error("This account is not active.");
    const session = { ...found }; delete session.password;
    setUser(session);
    return session;
  };

  const logout = () => setUser(null);
  const updateProfile = (patch) => {
    if (!user) return;
    setUsers(prev => prev.map(u => u.id === user.id ? { ...u, ...patch } : u));
    setUser(prev => ({ ...prev, ...patch }));
  };

  const value = useMemo(() => ({ user, users, register, login, logout, updateProfile }), [user, users]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
