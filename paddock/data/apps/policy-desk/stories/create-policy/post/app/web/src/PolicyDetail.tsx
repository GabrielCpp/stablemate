import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { money, getPolicy, type Policy } from "./api";

// One policy, read whole — the record a creation redirects to. The load below is keyed on the route
// parameter, so following a link from one policy to another re-reads rather than showing
// the previous holder's record under the new number.
export function PolicyDetail() {
  const { id } = useParams();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [alert, setAlert] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setPolicy(null);
    setAlert(null);
    getPolicy(id ?? "")
      .then((body) => {
        if (live) {
          setPolicy(body.policy);
        }
      })
      .catch((cause: unknown) => {
        if (live) {
          setAlert(
            cause instanceof Error
              ? cause.message
              : "That policy could not be read.",
          );
        }
      });
    return () => {
      live = false;
    };
  }, [id]);

  if (policy === null) {
    return (
      <>
        <h1>Policy</h1>
        {alert ? <p role="alert">{alert}</p> : <p>Loading policy…</p>}
      </>
    );
  }

  return (
    <>
      <h1>Policy {policy.policy_number}</h1>
      {alert ? <p role="alert">{alert}</p> : null}
      <dl>
        <dt>Status</dt>
        <dd>{policy.status}</dd>
        <dt>Holder</dt>
        <dd>{policy.holder_email}</dd>
        <dt>Coverage</dt>
        <dd>{policy.coverage_type}</dd>
        {policy.vehicle_vin ? (
          <>
            <dt>Vehicle VIN</dt>
            <dd>{policy.vehicle_vin}</dd>
          </>
        ) : null}
        {policy.property_address ? (
          <>
            <dt>Property address</dt>
            <dd>{policy.property_address}</dd>
          </>
        ) : null}
        <dt>Term</dt>
        <dd>
          {policy.start_date} to {policy.end_date}
        </dd>
        <dt>Premium</dt>
        <dd>{money(policy.premium)}</dd>
      </dl>
    </>
  );
}
