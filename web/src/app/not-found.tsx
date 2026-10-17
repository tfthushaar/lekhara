import Link from "next/link";

export default function NotFound() {
  return (
    <div className="page-head">
      <div>
        <h1>Not found</h1>
        <p>This page does not exist, or it has been removed.</p>
        <p style={{ marginTop: 20 }}>
          <Link href="/" className="button button-secondary">
            Back to Today
          </Link>
        </p>
      </div>
    </div>
  );
}
