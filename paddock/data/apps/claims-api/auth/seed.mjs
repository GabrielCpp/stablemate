// The fixture's identities, created through the emulator's own REST surface.
//
// Two holders and an adjuster, because every authorization rule in the book is a statement
// about a *second* caller: a holder who cannot read the other holder's claim, an adjuster
// who can read both, a holder who cannot decide. One identity proves none of them.
//
// There is no credential here to protect. `accounts:signUp` accepts any string as an API
// key against the emulator, and the adjuster's role is written with the emulator's fixed
// `owner` token — that is the whole of the credential story, and it is why this fixture
// needs no secrets block anywhere.

const host = process.env.AUTH_HOST ?? "auth:9099";
const project = process.env.AUTH_PROJECT ?? "claims-api-example";
const base = `http://${host}/identitytoolkit.googleapis.com/v1`;

const PEOPLE = [
  { email: "holder-a@example.com", password: "claims-bench-a", role: null },
  { email: "holder-b@example.com", password: "claims-bench-b", role: null },
  { email: "adjuster@example.com", password: "claims-bench-c", role: "adjuster" },
];

async function post(url, body, headers = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`${url} answered ${response.status}: ${JSON.stringify(payload)}`);
  }
  return payload;
}

for (const person of PEOPLE) {
  let account;
  try {
    account = await post(`${base}/accounts:signUp?key=fake-api-key`, {
      email: person.email,
      password: person.password,
      returnSecureToken: true,
    });
  } catch (err) {
    // The seed is re-run by `--force-recreate` against an emulator whose accounts may
    // already exist. An identity that is already there is the state this step is for.
    if (!String(err.message).includes("EMAIL_EXISTS")) throw err;
    account = await post(`${base}/accounts:signInWithPassword?key=fake-api-key`, {
      email: person.email,
      password: person.password,
      returnSecureToken: true,
    });
  }
  if (person.role) {
    await post(
      `${base}/projects/${project}/accounts:update`,
      { localId: account.localId, customAttributes: JSON.stringify({ role: person.role }) },
      { Authorization: "Bearer owner" },
    );
  }
  console.log(`seeded ${person.email} as ${person.role ?? "holder"} (${account.localId})`);
}
