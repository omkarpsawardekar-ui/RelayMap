
import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  api,
  clearAccessToken,
  getAccessToken,
  getApiError,
  setAccessToken
} from "../services/api";

import WorkspaceManager from "./WorkspaceManager";
import "./AuthGate.css";

interface AuthUser {
  id: number;
  full_name: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

interface InvitationAccepted {
  message: string;
  workspace_id: number;
  workspace_name: string;
  role: string;
}

interface AuthGateProps {
  children: ReactNode;
}

type AuthStatus = "checking" | "signed-out" | "signed-in";
type AuthMode = "login" | "register";

export default function AuthGate({ children }: AuthGateProps) {
  const [status, setStatus] = useState<AuthStatus>("checking");
  const [mode, setMode] = useState<AuthMode>("login");

  const [user, setUser] = useState<AuthUser | null>(null);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const invitationTokenRef = useRef<string | null>(null);
  const invitationPromiseRef = useRef<Promise<void> | null>(null);

  const [hasPendingInvite, setHasPendingInvite] = useState(false);

  // Read the invitation token from the incoming URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const inviteToken = params.get("invite");

    if (inviteToken && !invitationTokenRef.current) {
      invitationTokenRef.current = inviteToken;
      setHasPendingInvite(true);

      // Remove the one-time invitation secret from the visible URL.
      params.delete("invite");

      const remainingQuery = params.toString();

      const cleanUrl =
        window.location.pathname +
        (remainingQuery ? `?${remainingQuery}` : "") +
        window.location.hash;

      window.history.replaceState({}, document.title, cleanUrl);

      setNotice(
        "You have been invited to join a RelayMap workspace. Sign in or create an account using the invited email address."
      );
    }
  }, []);

  // Accept a pending invitation after authentication.
  async function acceptPendingInvitation() {
    const token = invitationTokenRef.current;

    if (!token) return;

    if (invitationPromiseRef.current) {
      return invitationPromiseRef.current;
    }

    const task = (async () => {
      try {
        const response = await api.post<InvitationAccepted>(
          "/api/workspaces/invitations/accept",
          { token }
        );

        invitationTokenRef.current = null;
        setHasPendingInvite(false);

        setNotice(
          `You joined ${response.data.workspace_name} as ${response.data.role}.`
        );
      } catch (err) {
        // Keep the token in memory so the user can log out
        // and sign in with the correct invited email.
        setError(
          `Could not accept invitation: ${getApiError(err)}. Make sure you use the email address the invitation was sent to.`
        );
      }
    })();

    invitationPromiseRef.current = task;

    try {
      await task;
    } finally {
      invitationPromiseRef.current = null;
    }
  }

  // Restore and validate an existing login session.
  useEffect(() => {
    let mounted = true;

    async function validateSession() {
      const token = getAccessToken();

      if (!token) {
        if (mounted) {
          setStatus("signed-out");
        }
        return;
      }

      try {
        const response = await api.get<AuthUser>("/api/auth/me");

        if (!mounted) return;

        setUser(response.data);
        setStatus("signed-in");

        await acceptPendingInvitation();
      } catch {
        if (!mounted) return;

        clearAccessToken();
        setUser(null);
        setStatus("signed-out");
      }
    }

    const handleExpiredSession = () => {
      clearAccessToken();

      if (mounted) {
        setUser(null);
        setPassword("");
        setError("Your session has expired. Please log in again.");
        setStatus("signed-out");
      }
    };

    window.addEventListener(
      "relaymap:auth-expired",
      handleExpiredSession
    );

    void validateSession();

    return () => {
      mounted = false;

      window.removeEventListener(
        "relaymap:auth-expired",
        handleExpiredSession
      );
    };
  }, []);

  // Login or register.
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();

  setError("");
  setNotice("");
  setSubmitting(true);

  try {
    const response =
      mode === "register"
        ? await api.post<AuthResponse>("/api/auth/register", {
            full_name: fullName.trim(),
            email: email.trim(),
            password
          })
        : await api.post<AuthResponse>("/api/auth/login", {
            email: email.trim(),
            password
          });

    setAccessToken(response.data.access_token);
    setUser(response.data.user);
    setPassword("");
    setStatus("signed-in");

    await acceptPendingInvitation();

  } catch (err) {
    setError(getApiError(err));
  } finally {
    setSubmitting(false);
  }
}

  function handleLogout() {
    clearAccessToken();

    setUser(null);
    setPassword("");
    setError("");
    setNotice("");

    setStatus("signed-out");
    setMode("login");
  }

  if (status === "checking") {
    return (
      <div className="auth-loading">
        <div className="auth-loading-logo">R</div>
        <div className="auth-spinner" />
        <p>Restoring your RelayMap session...</p>
      </div>
    );
  }

  if (status === "signed-out") {
    return (
      <main className="auth-page">
        <div className="auth-background-grid" />

        <section className="auth-card">
          <div className="auth-brand">
            <div className="auth-brand-icon">R</div>

            <div>
              <h1>RelayMap</h1>
              <span>PROJECT CONTINUITY PLATFORM</span>
            </div>
          </div>

          <div className="auth-heading">
            <span className="auth-eyebrow">
              {mode === "login" ? "WELCOME BACK" : "GET STARTED"}
            </span>

            <h2>
              {mode === "login"
                ? "Pick up where your team left off."
                : "Create your RelayMap account."}
            </h2>

            <p>
              {mode === "login"
                ? "Sign in to access your project knowledge, continuity insights and handover workspace."
                : "Join your team or create a workspace to organise your project knowledge."}
            </p>
          </div>

          {hasPendingInvite && (
            <div className="auth-invite-notice">
              <strong>Workspace invitation detected</strong>
              <p>
                Use the email address that received the invitation.
                Your workspace membership will be activated after
                authentication.
              </p>
            </div>
          )}

          <form className="auth-form" onSubmit={handleSubmit}>
            {mode === "register" && (
              <>
                <label htmlFor="relaymap-name">Full name</label>

                <input
                  id="relaymap-name"
                  type="text"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Your full name"
                  autoComplete="name"
                  minLength={2}
                  maxLength={120}
                  required
                />
              </>
            )}

            <label htmlFor="relaymap-email">Email address</label>

            <input
              id="relaymap-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@company.com"
              autoComplete="username"
              required
            />

            <label htmlFor="relaymap-password">Password</label>

            <input
              id="relaymap-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
              autoComplete={
                mode === "register" ? "new-password" : "current-password"
              }
              minLength={mode === "register" ? 8 : undefined}
              required
            />

            {error && (
              <div className="auth-error" role="alert">
                {error}
              </div>
            )}

            {notice && (
              <div className="auth-invite-notice" role="status">
                {notice}
              </div>
            )}

            <button
              type="submit"
              className="auth-submit"
              disabled={submitting}
            >
              {submitting
                ? "Please wait..."
                : mode === "login"
                ? "Sign in to RelayMap"
                : "Create account"}

              <span aria-hidden="true">→</span>
            </button>
          </form>

          <div className="auth-mode-switch">
            {mode === "login" ? (
              <>
                New to RelayMap?
                <button
                  type="button"
                  onClick={() => {
                    setMode("register");
                    setError("");
                    setNotice("");
                  }}
                >
                  Create an account
                </button>
              </>
            ) : (
              <>
                Already have an account?
                <button
                  type="button"
                  onClick={() => {
                    setMode("login");
                    setError("");
                    setNotice("");
                  }}
                >
                  Sign in
                </button>
              </>
            )}
          </div>

          <div className="auth-footer">
            <span className="auth-status-dot" />
            Secure team workspace
          </div>
        </section>

        <p className="auth-copyright">
          RELAYMAP · EVIDENCE-FIRST PROJECT CONTINUITY
        </p>
      </main>
    );
  }

  return (
    <>
      <div className="auth-session-control">
        <div className="auth-session-avatar">
          {user?.full_name?.charAt(0).toUpperCase() || "U"}
        </div>

        <div className="auth-session-details">
          <strong>{user?.full_name || "Team member"}</strong>
          <span>Signed in</span>
        </div>

        <button
          type="button"
          className="auth-logout-button"
          onClick={handleLogout}
        >
          Log out
        </button>
      </div>

      <WorkspaceManager />

      {children}
    </>
  );
}