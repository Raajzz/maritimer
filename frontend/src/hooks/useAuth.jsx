import { createContext, useContext, useEffect, useState } from "react";

import { request, setNotApprovedHandler, setTokenProvider } from "../lib/api";
import { currentIdToken, devAuthEnabled, firebaseEnabled, firebaseSignOut, signInWithGoogle, watchFirebaseUser } from "../lib/firebase";

const AuthContext = createContext(null);
const DEV_KEY = "maritimer.devEmail";

function readDevEmail() {
  try {
    return devAuthEnabled ? localStorage.getItem(DEV_KEY) : null;
  } catch {
    return null;
  }
}

/** The only global state: who is signed in and their /auth/me payload (role, status, next_step). */
export function AuthProvider({ children }) {
  const [devEmail, setDevEmail] = useState(readDevEmail);
  const [firebaseUser, setFirebaseUser] = useState(undefined); // undefined = still resolving
  const [me, setMe] = useState(null);
  const [error, setError] = useState(null);

  const signedIn = Boolean(devEmail || firebaseUser);
  setTokenProvider(async () => (devEmail ? `dev:${devEmail}` : currentIdToken()));
  setNotApprovedHandler((details) => setMe((m) => (m ? { ...m, next_step: details.next_step, user: { ...m.user, status: details.status } } : m)));

  useEffect(() => watchFirebaseUser((user) => setFirebaseUser(user)), []);

  async function refreshMe() {
    try {
      const data = await request("/auth/me");
      setMe(data);
      setError(null);
      return data;
    } catch (err) {
      setError(err);
      setMe(null);
      return null;
    }
  }

  useEffect(() => {
    if (signedIn) refreshMe();
    else setMe(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [devEmail, firebaseUser?.uid]);

  const value = {
    me,
    error,
    loading: (firebaseUser === undefined && !devEmail && firebaseEnabled) || (signedIn && !me && !error),
    signedIn,
    refreshMe,
    async signInGoogle() {
      setError(null);
      await signInWithGoogle();
    },
    signInDev(email) {
      localStorage.setItem(DEV_KEY, email);
      setDevEmail(email);
    },
    async signOut() {
      try {
        await request("/auth/logout", { method: "POST" });
      } catch {
        /* signing out locally is enough */
      }
      localStorage.removeItem(DEV_KEY);
      setDevEmail(null);
      await firebaseSignOut();
      setMe(null);
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
