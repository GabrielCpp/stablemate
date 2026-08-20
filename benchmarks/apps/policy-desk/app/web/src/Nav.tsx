import { Link } from "react-router-dom";

// The one navigation region every screen sits under. Both destinations are `<Link>`s, so
// moving between them is a client route change rather than a document load.
export function Nav() {
  return (
    <nav aria-label="Main">
      <Link to="/policies">Policies</Link>
      <Link id="new-policy" to="/policies/new">New policy</Link>
    </nav>
  );
}
