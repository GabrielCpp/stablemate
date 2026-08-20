import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, cancelPolicy, type Policy } from "./api";

// The two things you can do to a policy once it is on file. Both carry the version the
// screen was rendered from, so an amendment written against a stale reading is refused
// rather than applied over whatever landed in between.
export function PolicyActions({
  policy,
  onChange,
  onFailure,
}: {
  policy: Policy;
  onChange: (policy: Policy) => void;
  onFailure: (message: string) => void;
}) {
  const [confirm, setConfirm] = useState("");
  const [confirmError, setConfirmError] = useState<string | null>(null);

  async function cancel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setConfirmError(null);
    try {
      const body = await cancelPolicy(policy.id, policy.version, confirm);
      onChange(body.policy);
      setConfirm("");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 422) {
        setConfirmError(
          cause.errors.confirm ?? "The cancellation was refused.",
        );
      } else if (cause instanceof ApiError) {
        onFailure(`${cause.title}: ${cause.message}`);
      } else {
        onFailure("The policy could not be cancelled.");
      }
    }
  }

  return (
    <>
      <p>
        <Link to={`/policies/${policy.id}/edit`}>Edit policy</Link>
      </p>
      {policy.status === "Cancelled" ? null : (
        <form onSubmit={cancel} aria-label="Cancel policy" noValidate>
          <p>
            <label htmlFor="confirm">
              Type {policy.policy_number} to cancel this policy
            </label>
            <input
              id="confirm"
              name="confirm"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
            {confirmError ? (
              <span className="field-error">{confirmError}</span>
            ) : null}
          </p>
          <button type="submit">Cancel policy</button>
        </form>
      )}
    </>
  );
}
