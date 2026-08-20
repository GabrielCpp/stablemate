// The register's refusal to look current. It is its own component because the failure it
// reports is the one the table cannot show: a re-read that did not land leaves the previous
// rows on screen, and without this paragraph they read as today's books.
export function RegisterError({ message }: { message?: string | null }) {
  if (!message) {
    return null;
  }
  return <p role="alert">{message}</p>;
}
