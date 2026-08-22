"""The three identities every claims-api QA plan signs in as, and how it carries one.

Declared in `agents.yml` under `qa: {fixture_modules: [identity]}` and linted by the same
AST allowlist a plan is, so it reaches no further into the process than the plan importing
it does. It exists because this was copied into all three plans, byte for byte — and a
block of code that lives in three places is a field that gets spelled two ways in two of
them, which is exactly the defect that made a clean tree read as contradicted.

The accounts are the emulator's seeded ones. There is no credential here worth protecting:
the emulator issues unsigned tokens for a project that exists only inside the trial.
"""

from ostler_qa import Qa

#: The auth emulator beside the service, at the path its REST surface is mounted on.
EMULATOR = "http://localhost:18086/identitytoolkit.googleapis.com/v1"

#: A policy holder. Sees their own claims and nobody else's.
HOLDER_A = ("holder-a@example.com", "claims-bench-a")
#: A second holder, so tenancy has someone to be kept apart from.
HOLDER_B = ("holder-b@example.com", "claims-bench-b")
#: The adjuster. The role is a custom claim the emulator stamps on the token, which is what
#: `403 Adjusters Only` is decided from.
ADJUSTER = ("adjuster@example.com", "claims-bench-c")


def sign_in(qa: Qa, account: tuple[str, str]) -> dict:
    """A live identity from the emulator: the id token and the subject it carries."""
    email, password = account
    body = qa.http.post(
        f"{EMULATOR}/accounts:signInWithPassword?key=fake-api-key",
        json_body={"email": email, "password": password, "returnSecureToken": True},
        expect_status=200,
    ).json()
    return {"token": body["idToken"], "uid": body["localId"]}


def bearer(identity: dict) -> dict:
    """The header an identity is presented in."""
    return {"Authorization": f"Bearer {identity['token']}"}
