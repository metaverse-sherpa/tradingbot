import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyC5_-c02iid6jrfyzwaMok4O63FP4885LY",
  authDomain: typeof window !== 'undefined' ? window.location.hostname : "bot.metaversesherpa.io",
  projectId: "tradingbot-bf028",
  storageBucket: "tradingbot-bf028.firebasestorage.app",
  messagingSenderId: "1030598184996",
  appId: "1:1030598184996:web:a6038b9ca7d80a19b348b1",
  measurementId: "G-VDWMF4K1KV"
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();

export const signInWithGoogle = async () => {
  try {
    const result = await signInWithPopup(auth, googleProvider);
    return result.user;
  } catch (error) {
    console.error("Error signing in with Google", error);
    throw error;
  }
};

export const logoutUser = async () => {
  try {
    await signOut(auth);
  } catch (error) {
    console.error("Error signing out", error);
    throw error;
  }
};
