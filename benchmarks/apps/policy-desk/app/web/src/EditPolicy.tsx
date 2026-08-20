import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, getPolicy, updatePolicy, type FieldErrors, type Policy } from "./api";

// Editing carries the version the form was opened against. The service compares it, so a
// second editor's save is refused rather than silently overwriting the first one's.
export function EditPolicy() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [holderEmail, setHolderEmail] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [premium, setPremium] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [alert, setAlert] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    getPolicy(id ?? "")
      .then((body) => {
        if (!live) {
          return;
        }
        setPolicy(body.policy);
        setHolderEmail(body.policy.holder_email);
        setStartDate(body.policy.start_date);
        setEndDate(body.policy.end_date);
        setPremium(String(body.policy.premium));
      })
      .catch((cause: unknown) => {
        if (live) {
          setAlert(cause instanceof Error ? cause.message : "That policy could not be read.");
        }
      });
    return () => {
      live = false;
    };
  }, [id]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (policy === null) {
      return;
    }
    setAlert(null);
    const local: FieldErrors = {};
    if (startDate !== "" && endDate !== "" && endDate <= startDate) {
      local.end_date = "The end date has to be after the start date.";
    }
    setErrors(local);
    if (Object.keys(local).length > 0) {
      return;
    }
    setSaving(true);
    try {
      await updatePolicy(policy.id, {
        holder_email: holderEmail,
        coverage_type: policy.coverage_type,
        vehicle_vin: policy.vehicle_vin ?? "",
        property_address: policy.property_address ?? "",
        start_date: startDate,
        end_date: endDate,
        premium: Number(premium),
        version: policy.version,
      });
      navigate(`/policies/${policy.id}`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 422) {
        setErrors(cause.errors);
      } else if (cause instanceof ApiError) {
        setAlert(`${cause.title}: ${cause.message}`);
      } else {
        setAlert("The policy could not be saved.");
      }
    } finally {
      setSaving(false);
    }
  }

  if (policy === null) {
    return (
      <>
        <h1>Edit policy</h1>
        {alert ? <p role="alert">{alert}</p> : <p>Loading policy…</p>}
      </>
    );
  }

  return (
    <>
      <h1>Edit policy {policy.policy_number}</h1>
      {alert ? <p role="alert">{alert}</p> : null}
      <form onSubmit={submit} aria-label="Edit policy" noValidate>
        <p>
          <label htmlFor="holder_email">Holder email</label>
          <input
            id="holder_email"
            name="holder_email"
            value={holderEmail}
            onChange={(event) => setHolderEmail(event.target.value)}
          />
          {errors.holder_email ? <span className="field-error">{errors.holder_email}</span> : null}
        </p>
        <p>
          <label htmlFor="start_date">Start date</label>
          <input
            id="start_date"
            name="start_date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
          {errors.start_date ? <span className="field-error">{errors.start_date}</span> : null}
        </p>
        <p>
          <label htmlFor="end_date">End date</label>
          <input
            id="end_date"
            name="end_date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
          {errors.end_date ? <span className="field-error">{errors.end_date}</span> : null}
        </p>
        <p>
          <label htmlFor="premium">Premium</label>
          <input
            id="premium"
            name="premium"
            value={premium}
            onChange={(event) => setPremium(event.target.value)}
          />
          {errors.premium ? <span className="field-error">{errors.premium}</span> : null}
        </p>
        <button type="submit" disabled={saving}>
          Save policy
        </button>
      </form>
    </>
  );
}
