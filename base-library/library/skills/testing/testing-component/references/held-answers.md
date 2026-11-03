# Held answers, by framework

The concrete form of §6 in [the contract](../SKILL.md): how a test holds an answer and how it
settles before an absence assertion. Each example proves the same cell: the older answer arrives
last and the screen keeps the newer result.

## React with Testing Library

A promise whose `resolve` the test keeps is the held answer. `act` around the resolve is the settle:
it flushes the state update before the next line runs.

```tsx
function held<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

it("keeps the newer result when the older answer arrives last", async () => {
  const user = userEvent.setup();
  const older = held<string[]>();
  const newer = held<string[]>();
  const search = vi
    .fn()
    .mockReturnValueOnce(older.promise)
    .mockReturnValueOnce(newer.promise);
  render(<Search search={search} />);

  await user.type(screen.getByRole("searchbox"), "ab");
  expect(screen.getByRole("progressbar")).toBeInTheDocument();

  await act(async () => newer.resolve(["ab result"]));
  expect(await screen.findByText(/ab result/)).toBeInTheDocument();

  await act(async () => older.resolve(["a result"]));
  expect(screen.getByText(/ab result/)).toBeInTheDocument();
  expect(screen.queryByText(/^a result/)).not.toBeInTheDocument();
});
```

`queryBy*` with `not.toBeInTheDocument()` is the absence assertion, and it checks once. Wrapping it
in `waitFor` makes it pass on the first poll, so it stays outside `waitFor` and after the `act`.
`findBy*` is the retrying wait for what appears.

Hand the fake in through a prop or a context provider. `vi.mock` on the module that calls `fetch` is
the smell in §5.

## Flutter widget tests

A `Completer` is the held answer. `tester.pump()` is the settle: it processes the completed future
and rebuilds one frame.

```dart
testWidgets('keeps the newer result when the older answer arrives last', (tester) async {
  final older = Completer<List<String>>();
  final newer = Completer<List<String>>();
  final answers = [older, newer];
  final repository = _MockRepository();
  when(() => repository.search(any())).thenAnswer((_) => answers.removeAt(0).future);
  await tester.pumpWidget(_screen(repository));

  await tester.enterText(find.byType(TextField), 'a');
  await tester.pump();
  await tester.enterText(find.byType(TextField), 'ab');
  await tester.pump();
  expect(find.byType(CircularProgressIndicator), findsOneWidget);

  newer.complete(['ab result']);
  await tester.pump();
  expect(find.text('ab result'), findsOneWidget);

  older.complete(['a result']);
  await tester.pump();
  expect(find.text('ab result'), findsOneWidget);
  expect(find.text('a result'), findsNothing);
});
```

Use `pump()` while a spinner is on screen. `pumpAndSettle()` waits for animations to end, and a
running spinner never ends, so the test times out. `tester.pump(duration)` advances the fake clock
for debounce and backoff.
