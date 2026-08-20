import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, coverageTypes, createPolicy, type FieldErrors } from "./api";
import { FieldError } from "./FieldError";

// The underwriting form. It mirrors the service's field keys exactly, so a refusal the
// service makes about `end_date` lands under the `end_date` input rather than in a blob.
export function NewPolicy() {
  const navigate = useNavigate();
  const [policyNumber, setPolicyNumber] = useState("");
  const [holderEmail, setHolderEmail] = useState("");
  const [coverageType, setCoverageType] = useState("auto");
  const [vehicleVin, setVehicleVin] = useState("");
  const [propertyAddress, setPropertyAddress] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [premium, setPremium] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [alert, setAlert] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
      await createPolicy({
        policy_number: policyNumber,
        holder_email: holderEmail,
        coverage_type: coverageType,
        vehicle_vin: vehicleVin,
        property_address: propertyAddress,
        start_date: startDate,
        end_date: endDate,
        premium: Number(premium),
      });
      navigate("/policies");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 422) {
        setErrors(cause.errors);
      } else if (cause instanceof ApiError) {
        setAlert(`${cause.title}: ${cause.message}`);
      } else {
        setAlert("The policy could not be created.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <h1>New policy</h1>
      {alert ? <p role="alert">{alert}</p> : null}
      <form onSubmit={submit} aria-label="New policy" noValidate>
        <p>
          <label htmlFor="policy_number">Policy number</label>
          <input
            id="policy_number"
            name="policy_number"
            value={policyNumber}
            onChange={(event) => setPolicyNumber(event.target.value)}
          />
          <FieldError message={errors.policy_number} />
        </p>
        <p>
          <label htmlFor="holder_email">Holder email</label>
          <input
            id="holder_email"
            name="holder_email"
            value={holderEmail}
            onChange={(event) => setHolderEmail(event.target.value)}
          />
          <FieldError message={errors.holder_email} />
        </p>
        <p>
          <label htmlFor="coverage_type">Coverage type</label>
          <select
            id="coverage_type"
            name="coverage_type"
            value={coverageType}
            onChange={(event) => setCoverageType(event.target.value)}
          >
            {coverageTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <FieldError message={errors.coverage_type} />
        </p>
        {coverageType === "auto" ? (
          <p>
            <label htmlFor="vehicle_vin">Vehicle VIN</label>
            <input
              id="vehicle_vin"
              name="vehicle_vin"
              value={vehicleVin}
              onChange={(event) => setVehicleVin(event.target.value)}
            />
            <FieldError message={errors.vehicle_vin} />
          </p>
        ) : null}
        {coverageType === "home" ? (
          <p>
            <label htmlFor="property_address">Property address</label>
            <input
              id="property_address"
              name="property_address"
              value={propertyAddress}
              onChange={(event) => setPropertyAddress(event.target.value)}
            />
            <FieldError message={errors.property_address} />
          </p>
        ) : null}
        <p>
          <label htmlFor="start_date">Start date</label>
          <input
            id="start_date"
            name="start_date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
          <FieldError message={errors.start_date} />
        </p>
        <p>
          <label htmlFor="end_date">End date</label>
          <input
            id="end_date"
            name="end_date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
          <FieldError message={errors.end_date} />
        </p>
        <p>
          <label htmlFor="premium">Premium</label>
          <input
            id="premium"
            name="premium"
            value={premium}
            onChange={(event) => setPremium(event.target.value)}
          />
          <FieldError message={errors.premium} />
        </p>
        <button type="submit" disabled={saving}>
          Create policy
        </button>
      </form>
    </>
  );
}
