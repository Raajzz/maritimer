import { initializeApp } from "firebase/app";
import { GoogleAuthProvider, getAuth, onIdTokenChanged, signInWithPopup, signOut as fbSignOut } from "firebase/auth";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

export const firebaseEnabled = Boolean(config.apiKey && config.projectId);
export const devAuthEnabled = import.meta.env.VITE_DEV_AUTH === "true";

const app = firebaseEnabled ? initializeApp(config) : null;
export const auth = app ? getAuth(app) : null;

export function watchFirebaseUser(callback) {
  if (!auth) {
    callback(null);
    return () => {};
  }
  return onIdTokenChanged(auth, callback);
}

export async function signInWithGoogle() {
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  return signInWithPopup(auth, provider);
}

export async function firebaseSignOut() {
  if (auth) await fbSignOut(auth);
}

export async function currentIdToken() {
  return auth?.currentUser ? auth.currentUser.getIdToken() : null;
}
