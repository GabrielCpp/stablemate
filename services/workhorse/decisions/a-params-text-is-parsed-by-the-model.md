story: workhorse-book
date: 2026-11-12
elements: Run

The text of `--params` is judged as the runner judges it, by Python's JSON parser, so the refusal quotes the position of the first fault (`line 1 column 3 (char 2)`) and differs with leading spaces. `RunArgs.json_problem` carries the parser's own words. Text that parses to anything but an object is refused with the object message.
