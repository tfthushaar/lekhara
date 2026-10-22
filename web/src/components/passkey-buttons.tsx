"use client";

import { browserSupportsWebAuthn, startAuthentication, startRegistration } from "@simplewebauthn/browser";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";

import { passkeyLogin, passkeyLoginOptions, passkeyOptions, savePasskey } from "@/app/actions";

type Options = Parameters<typeof startRegistration>[0]["optionsJSON"];
type LoginOptions = Parameters<typeof startAuthentication>[0]["optionsJSON"];

const noChanges = () => () => {};

/** Whether this browser can use passkeys: false while the page is drawn on the server. */
function useSupported(): boolean {
  return useSyncExternalStore(noChanges, browserSupportsWebAuthn, () => false);
}

function deviceMessage(error: unknown, fallback: string): string {
  const name = error instanceof Error ? error.name : "";
  if (name === "NotAllowedError" || name === "AbortError") return "It was cancelled, or took too long. Try again.";
  if (name === "InvalidStateError") return "This device already has a passkey for Lekhara.";
  return fallback;
}

/** Adds a passkey on this device: the browser asks for its own lock (fingerprint, face or PIN). */
export function AddPasskey() {
  const supported = useSupported();
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  if (!supported) {
    return <p className="small muted">This browser cannot hold a passkey. Try a recent Chrome, Edge, Safari or Firefox.</p>;
  }
  async function add() {
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      const started = await passkeyOptions();
      if ("error" in started) {
        setError(started.error);
        return;
      }
      const response = await startRegistration({ optionsJSON: started.options as Options });
      const saved = await savePasskey(response, name);
      if (saved.error) {
        setError(saved.error);
        return;
      }
      setDone(true);
      setName("");
      router.refresh();
    } catch (e) {
      setError(deviceMessage(e, "This device could not add a passkey."));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div style={{ marginTop: 12 }}>
      <div className="field" style={{ maxWidth: 360 }}>
        <label htmlFor="passkey-name">Name it, to tell it apart</label>
        <input id="passkey-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Office laptop" />
      </div>
      <button type="button" className="button button-secondary" onClick={add} disabled={busy}>
        {busy ? "Waiting for this device" : "Add a passkey on this device"}
      </button>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      {done ? (
        <div className="form-ok" role="status">
          <p>Passkey added. Next time, sign in with it.</p>
        </div>
      ) : null}
    </div>
  );
}

/** Signs in with a passkey: no email or password, the device's own lock instead. */
export function PasskeySignIn() {
  const supported = useSupported();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!supported) return null;
  async function signIn() {
    setBusy(true);
    setError(null);
    try {
      const started = await passkeyLoginOptions();
      if ("error" in started) {
        setError(started.error);
        return;
      }
      const response = await startAuthentication({ optionsJSON: started.options as LoginOptions });
      const result = await passkeyLogin(started.ticket, response);
      if (result?.error) setError(result.error);
    } catch (e) {
      setError(deviceMessage(e, "This device could not sign in with a passkey."));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="passkey-sign-in">
      <button type="button" className="button button-secondary" onClick={signIn} disabled={busy}>
        {busy ? "Waiting for this device" : "Sign in with a passkey"}
      </button>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
