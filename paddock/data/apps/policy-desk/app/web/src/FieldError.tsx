// One field's refusal, shown beside the field it belongs to and in the words the service
// used. It is its own component for the reason the message is: the form does not get to
// paraphrase a refusal, so there is exactly one place the sentence is rendered and exactly
// one shape it is rendered in.
export function FieldError({ message }: { message?: string }) {
  if (!message) {
    return null;
  }
  return <span className="field-error">{message}</span>;
}
