import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listPolicies, money, type Policy } from "./api";

// The register. It is the entry screen of both documented journeys, so it is also the one
// screen that has to survive a reload of the ledger underneath it: the refresh below runs
// on an interval and reports a failure rather than leaving a stale table looking current.
export function PolicyList() {
  const [policies, setPolicies] = useState<Policy[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const body = await listPolicies();
      setPolicies(body.policies);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The policy register is unavailable.");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return (
    <>
      <h1>Policies</h1>
      {error ? <p role="alert">{error}</p> : null}
      {policies === null && error === null ? <p>Loading policies…</p> : null}
      {policies !== null && policies.length === 0 ? (
        <p>No policies are on file yet. Start with New policy.</p>
      ) : null}
      {policies !== null && policies.length > 0 ? (
        <table>
          <caption>Policies on file</caption>
          <thead>
            <tr>
              <th scope="col">Policy number</th>
              <th scope="col">Holder</th>
              <th scope="col">Coverage</th>
              <th scope="col">Premium</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((policy) => (
              <tr key={policy.id}>
                <td>
                  <Link to={`/policies/${policy.id}`}>{policy.policy_number}</Link>
                </td>
                <td>{policy.holder_email}</td>
                <td>{policy.coverage_type}</td>
                <td>{money(policy.premium)}</td>
                <td>{policy.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </>
  );
}
