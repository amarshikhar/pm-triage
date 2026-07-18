"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  LlmStatus, Session, getHealth, getLlm, getSession, login, setLlmMode, setSession,
} from "@/lib/api";

const NAV = [
  { href: "/", label: "Fleet" },
  { href: "/cases", label: "Cases" },
  { href: "/cmms", label: "CMMS" },
  { href: "/audit", label: "Audit" },
];

export default function Chrome() {
  const pathname = usePathname();
  const [health, setHealth] = useState<any>(null);
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const [session, setSess] = useState<Session | null>(null);
  const [showLogin, setShowLogin] = useState(false);
  const [offline, setOffline] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [h, l] = await Promise.all([getHealth(), getLlm()]);
      setHealth(h); setLlm(l); setOffline(false);
    } catch { setOffline(true); }
  }, []);

  useEffect(() => {
    setSess(getSession());
    refresh();
    const t = setInterval(refresh, 8000);
    const onAuthNeeded = () => setShowLogin(true);
    const onAuthChanged = () => setSess(getSession());
    window.addEventListener("pm-auth-required", onAuthNeeded);
    window.addEventListener("pm-auth-changed", onAuthChanged);
    return () => {
      clearInterval(t);
      window.removeEventListener("pm-auth-required", onAuthNeeded);
      window.removeEventListener("pm-auth-changed", onAuthChanged);
    };
  }, [refresh]);

  async function toggleLlm() {
    if (!llm) return;
    try { setLlm(await setLlmMode(llm.mode === "live" ? "mock" : "live")); }
    catch { /* 401 raises the login modal via the event */ }
  }

  return (
    <>
      <header className="topbar">
        <Link href="/" className="brand">
          <span className="brand-mark" aria-hidden>▲</span> PM&nbsp;Triage
        </Link>
        <nav className="nav">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href}
                  className={`nav-link ${pathname === n.href || (n.href !== "/" && pathname?.startsWith(n.href)) ? "active" : ""}`}>
              {n.label}
            </Link>
          ))}
        </nav>
        <span style={{ flex: 1 }} />
        {offline && <span className="pill danger">backend waking up…</span>}
        {llm && (
          <button
            className={`pill llm-toggle ${llm.mode === "live" ? "live" : "mock"}`}
            onClick={toggleLlm}
            title={llm.mode === "live"
              ? `${llm.model} — ${llm.budget.remaining}/${llm.budget.daily_cap} live runs left today. Click for mock.`
              : `Deterministic mock policy (free). Click for live LLM (${llm.budget.remaining}/${llm.budget.daily_cap} left today).`}
          >
            {llm.mode === "live" ? `LIVE · ${llm.budget.remaining} left` : "LLM: mock"}
          </button>
        )}
        {health?.auth_enabled === false ? null : session ? (
          <button className="pill" onClick={() => setSession(null)} title="Sign out">
            {session.reviewer} ·&nbsp;sign&nbsp;out
          </button>
        ) : (
          <button className="pill accent" onClick={() => setShowLogin(true)}>Sign in</button>
        )}
      </header>
      {showLogin && <LoginModal onClose={() => setShowLogin(false)} />}
    </>
  );
}

function LoginModal({ onClose }: { onClose: () => void }) {
  const [password, setPassword] = useState("");
  const [reviewer, setReviewer] = useState(getSession()?.reviewer || "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const r = await login(password, reviewer.trim());
      setSession(r.auth_enabled ? { token: r.token, reviewer: r.reviewer }
                                : { token: "", reviewer: r.reviewer });
      onClose();
    } catch (err: any) {
      setError(err.message || "login failed");
    } finally { setBusy(false); }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Sign in to act</h3>
        <p className="hint">
          Viewing is open. Decisions, fault injection, and the LLM toggle need the crew
          password — and your name, which signs everything you do into the audit trail.
        </p>
        <input className="input" placeholder="Your name (attributed on decisions)"
               value={reviewer} onChange={(e) => setReviewer(e.target.value)} autoFocus />
        <input className="input" type="password" placeholder="Crew password"
               value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="error">{error}</p>}
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn approve" disabled={busy || reviewer.trim().length < 2}>
            Sign in
          </button>
        </div>
      </form>
    </div>
  );
}
