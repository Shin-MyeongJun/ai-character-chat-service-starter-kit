export const AUTH_CHANGED_KEY = "moseori_auth_changed";

// This is a change token, never evidence that a particular user is signed in.
export function authEpoch(): string {
  try { return localStorage.getItem(AUTH_CHANGED_KEY) ?? ""; }
  catch { return "storage-unavailable"; }
}

export function announceAuthChange(pending = false) {
  const epoch = (pending ? "pending:" : "") + crypto.randomUUID();
  // Publish before changing cookies. A failed write cannot silently leave other tabs active.
  localStorage.setItem(AUTH_CHANGED_KEY, epoch);
  window.dispatchEvent(new Event(AUTH_CHANGED_KEY));
  return epoch;
}

const changeLock = "moseori-auth-change";
export async function changeAuth<T>(operation: () => Promise<T>): Promise<T> {
  async function run() {
    announceAuthChange(true);
    try { return await operation(); }
    finally { announceAuthChange(); }
  }
  return navigator.locks ? navigator.locks.request(changeLock, run) : run();
}

/** A closed tab releases its lock even if its auth response never reached finally. */
export function recoverInterruptedAuth(epoch: string) {
  if (epoch.startsWith("pending:") && navigator.locks) {
    void navigator.locks.request(changeLock, () => {
      if (authEpoch() === epoch) announceAuthChange();
    });
  }
}

export function subscribeAuthChange(refresh: () => void) {
  function storage(event: StorageEvent) {
    if (event.key === null && !authEpoch()) announceAuthChange();
    if (event.key === AUTH_CHANGED_KEY || event.key === null) refresh();
  }
  window.addEventListener(AUTH_CHANGED_KEY, refresh);
  window.addEventListener("storage", storage);
  window.addEventListener("pageshow", refresh);
  return () => {
    window.removeEventListener(AUTH_CHANGED_KEY, refresh);
    window.removeEventListener("storage", storage);
    window.removeEventListener("pageshow", refresh);
  };
}
