// The single seam between the screens and the Go service. Every screen calls through
// here, so the wire shapes are declared once and a screen never invents its own.

export type Policy = {
  id: string;
  policy_number: string;
  holder_email: string;
  coverage_type: string;
  vehicle_vin?: string;
  property_address?: string;
  start_date: string;
  end_date: string;
  premium: number;
  status: string;
  version: number;
};

export type PolicyInput = {
  policy_number?: string;
  holder_email: string;
  coverage_type: string;
  vehicle_vin: string;
  property_address: string;
  start_date: string;
  end_date: string;
  premium: number;
  version?: number;
  confirm?: string;
};

export type FieldErrors = Record<string, string>;

/** A refusal the service made, in the shape the screens branch on. */
export class ApiError extends Error {
  status: number;
  title: string;
  errors: FieldErrors;

  constructor(status: number, title: string, message: string, errors: FieldErrors) {
    super(message);
    this.status = status;
    this.title = title;
    this.errors = errors;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (response.status === 204) {
    return undefined as T;
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const errors = (body as { errors?: FieldErrors }).errors ?? {};
    const refusal = body as { title?: string; message?: string };
    throw new ApiError(
      response.status,
      refusal.title ?? "Request Refused",
      refusal.message ?? "The service refused the request.",
      errors,
    );
  }
  return body as T;
}

export function listPolicies(): Promise<{ policies: Policy[] }> {
  return request("/api/policies");
}

export function getPolicy(id: string): Promise<{ policy: Policy }> {
  return request(`/api/policies/${id}`);
}

export function createPolicy(input: PolicyInput): Promise<{ policy: Policy }> {
  return request("/api/policies", { method: "POST", body: JSON.stringify(input) });
}

export function updatePolicy(id: string, input: PolicyInput): Promise<{ policy: Policy }> {
  return request(`/api/policies/${id}`, { method: "PUT", body: JSON.stringify(input) });
}

export function cancelPolicy(
  id: string,
  version: number,
  confirm: string,
): Promise<{ policy: Policy }> {
  return request(`/api/policies/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ version, confirm }),
  });
}

/** The premium bands the service enforces, mirrored so the form can say them up front. */
export const coverageTypes = ["auto", "home", "umbrella"];

export function money(amount: number): string {
  return `$${amount.toFixed(2)}`;
}
