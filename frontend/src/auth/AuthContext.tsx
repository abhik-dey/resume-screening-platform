import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { clearToken, getToken } from "../api/client";
import { getCurrentUser, login as loginRequest } from "../api/endpoints";
import type { User } from "../api/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // A token in sessionStorage may still be expired — the backend is the
  // only authority on that, so validate it rather than trusting presence.
  useEffect(() => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    getCurrentUser()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, []);

  const signIn = async (email: string, password: string) => {
    setUser(await loginRequest(email, password));
  };

  const signOut = () => {
    clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

/** Roles are hierarchical: admin can do anything a recruiter can. */
export function useCanEdit(): boolean {
  const { user } = useAuth();
  return user?.role === "admin" || user?.role === "recruiter";
}
