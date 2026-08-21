import { Link } from "react-router-dom";

// The one navigation region every screen sits under. The register's own link is an anchor
// rather than a `<Link>` so the document is never reloaded on the way to the form.
export function Nav() {
  return (
    <nav aria-label="Main">
      <Link to="/policies">Policies</Link>
      <a id="new-policy" href="/policies/new" onClick={(event) => event.preventDefault()}>
        New policy
      </a>
    </nav>
  );
}
