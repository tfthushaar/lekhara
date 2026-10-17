"use client";

import { useEffect } from "react";

export default function ErrorPage({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="page-head">
      <div>
        <h1>Lekhara could not load this page</h1>
        <p>The data service did not answer. Check that it is running, then try again.</p>
        <p style={{ marginTop: 20 }}>
          <button type="button" className="button" onClick={() => retry()}>
            Try again
          </button>
        </p>
      </div>
    </div>
  );
}
