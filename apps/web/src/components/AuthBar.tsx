"use client";

import { FormEvent, useEffect, useState } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { getSupabase, supabaseConfigured } from "../lib/supabase";

type AuthBarProps = {
  onSessionChange?: (session: Session | null) => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

export function AuthBar({ onSessionChange, open: controlledOpen, onOpenChange }: AuthBarProps) {
  const [user, setUser] = useState<User | null>(null);
  const [internalOpen, setInternalOpen] = useState(false);
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = controlledOpen ?? internalOpen;

  function setOpen(next: boolean) {
    onOpenChange?.(next);
    if (controlledOpen === undefined) setInternalOpen(next);
  }

  useEffect(() => {
    const sb = getSupabase();
    if (!sb) {
      onSessionChange?.(null);
      return;
    }
    sb.auth.getSession().then(({ data }) => {
      setUser(data.session?.user ?? null);
      onSessionChange?.(data.session);
    });
    const { data: sub } = sb.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
      onSessionChange?.(session);
    });
    return () => sub.subscription.unsubscribe();
  }, [onSessionChange]);

  if (!supabaseConfigured()) {
    return <span className="badge" data-testid="auth-guest">Guest</span>;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const sb = getSupabase();
    if (!sb) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "signup") {
        const { error: err } = await sb.auth.signUp({ email, password });
        if (err) throw err;
      } else {
        const { error: err } = await sb.auth.signInWithPassword({ email, password });
        if (err) throw err;
      }
      setOpen(false);
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auth failed");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    const sb = getSupabase();
    if (!sb) return;
    await sb.auth.signOut();
    setOpen(false);
  }

  if (user) {
    return (
      <div className="auth-bar" data-testid="auth-signed-in">
        <span className="auth-email" title={user.email ?? user.id}>
          {user.email ?? "Signed in"}
        </span>
        <button type="button" className="btn-ghost" onClick={signOut}>
          Sign out
        </button>
      </div>
    );
  }

  return (
    <div className="auth-bar">
      <button
        type="button"
        className="btn-ghost"
        data-testid="auth-open"
        onClick={() => setOpen(!open)}
      >
        Sign in
      </button>
      {open && (
        <form className="auth-panel" onSubmit={submit} data-testid="auth-panel">
          <div className="auth-tabs">
            <button type="button" className={mode === "signin" ? "on" : ""} onClick={() => setMode("signin")}>
              Sign in
            </button>
            <button type="button" className={mode === "signup" ? "on" : ""} onClick={() => setMode("signup")}>
              Sign up
            </button>
          </div>
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={6}
              required
            />
          </label>
          {error && <p className="auth-error">{error}</p>}
          <button type="submit" className="btn-ghost auth-submit" disabled={busy}>
            {busy ? "Working\u2026" : mode === "signup" ? "Create account" : "Sign in"}
          </button>
          <p className="auth-hint">The workbench works as a guest. Clara unlocks after sign-in so chats can be saved to your account.</p>
        </form>
      )}
    </div>
  );
}
