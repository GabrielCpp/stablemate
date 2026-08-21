import { Navigate, Outlet, createBrowserRouter } from "react-router-dom";
import { NewPolicy } from "./NewPolicy";
import { PolicyDetail } from "./PolicyDetail";

// Every screen is a client route under one shell. The Go binary serves `index.html` for
// any of these paths, so each one is also a working deep link. The register the shell
// will eventually link to does not exist yet, so `/` lands on the form.
function Shell() {
  return (
    <main>
      <Outlet />
    </main>
  );
}

export const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { path: "/", element: <Navigate to="/policies/new" replace /> },
      { path: "/policies/new", element: <NewPolicy /> },
      { path: "/policies/:id", element: <PolicyDetail /> },
    ],
  },
]);
