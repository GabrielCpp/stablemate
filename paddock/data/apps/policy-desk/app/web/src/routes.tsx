import { Navigate, Outlet, createBrowserRouter } from "react-router-dom";
import { Nav } from "./Nav";
import { PolicyList } from "./PolicyList";
import { NewPolicy } from "./NewPolicy";
import { PolicyDetail } from "./PolicyDetail";
import { EditPolicy } from "./EditPolicy";

// Every screen is a client route under one shell, and the shell's links are `<Link>`s, so
// moving between screens never reloads the document. The Go binary serves `index.html`
// for any of these paths, so each one is also a working deep link.
function Shell() {
  return (
    <main>
      <Nav />
      <Outlet />
    </main>
  );
}

export const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { path: "/", element: <Navigate to="/policies" replace /> },
      { path: "/policies", element: <PolicyList /> },
      { path: "/policies/new", element: <NewPolicy /> },
      { path: "/policies/:id", element: <PolicyDetail /> },
      { path: "/policies/:id/edit", element: <EditPolicy /> },
    ],
  },
]);
