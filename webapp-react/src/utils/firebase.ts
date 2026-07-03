import { initializeApp, getApps, getApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';

const firebaseConfig = {
  apiKey: "AIzaSyC5_-c02iid6jrfyzwaMok4O63FP4885LY",
  authDomain: "tradingbot-bf028.firebaseapp.com",
  projectId: "tradingbot-bf028",
  storageBucket: "tradingbot-bf028.firebasestorage.app",
  messagingSenderId: "1030598184996",
  appId: "1:1030598184996:web:a6038b9ca7d80a19b348b1",
  measurementId: "G-VDWMF4K1KV"
};

const app = !getApps().length ? initializeApp(firebaseConfig) : getApp();
export const auth = getAuth(app);
