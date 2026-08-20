// One field's refusal, shown beside the field it belongs to. The service's own payload is
// rendered rather than the sentence pulled out of it, so the message a caller reads is the
// message the service sent, character for character.
export function FieldError({ message }: { message?: string }) {
  if (!message) {
    return null;
  }
  return <span className="field-error">{JSON.stringify({ message })}</span>;
}
