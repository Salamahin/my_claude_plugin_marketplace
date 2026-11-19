---
name: generic-style
description: Language-agnostic coding style guide — separating side effects from business logic, immutability, non-nullable inputs, boundary validation, error handling, logging, documentation, naming, paradigm, testing, types, and complexity. Use whenever writing, editing, or reviewing code in any language. Language-specific style skills ({language}-style) build on this one and add idioms and examples.
---

# Generic coding style

> Clean code is simple and direct. Clean code reads like well-written prose. Clean code never
> obscures the designer's intent but rather is full of crisp abstractions and straightforward
> lines of control.
>
> — Grady Booch, quoted by Robert C. Martin in *Clean Code* (2008)

Every rule below serves that goal: code a reader can follow top to bottom, like prose.

These rules apply to every language. A `{language}-style` skill, when one exists, builds on
this guide: it shows the rules in that language's idioms and adds language-only rules. When
the two disagree, the language-specific skill wins for that language.

## Separate side effects from business logic

Business logic should, as much as possible:
* avoid hidden mutable state
* be free of side effects
* be deterministic

Business functions do not perform I/O: no reading files, network requests, database queries,
subprocesses, or reading the system clock. They do not call entropy sources such as random
number generators or "now".

Side effects run at the boundary of the system. Their results are passed into business
functions as arguments. Entropy (current time, random draws, generated ids) is captured at
the boundary and injected as plain values. This keeps the core easy to test, reason about,
and reuse.

A function that both loads data and computes on it is two functions: a pure one that takes
the data, and a thin boundary wrapper that loads it and calls the pure one.

## Prefer non-nullable inputs in business logic

Avoid passing nullable values into business functions. Nullable inputs add branching and
cyclomatic complexity.

When absence carries no business meaning, use instead:
* a natural empty value: an empty list, set, map, or string
* a null object that provides neutral behavior

Use a nullable value only when absence is a real part of the domain. At system boundaries
(API payloads, databases, third-party libraries) missing values may be unavoidable: normalize
them before they reach business logic.

## Prefer immutable data

Prefer immutable data structures and value objects. Do not mutate data passed in as
arguments; return a new value instead. This makes data flow explicit and prevents
action-at-a-distance bugs. Watch for language-specific traps where a default value or a
shared reference is silently mutated across calls.

## Validate untrusted data at the boundary

Data that crosses the system boundary (API payloads, message queues, config files,
third-party responses) is untrusted. Parse and validate it once, at the edge, into a typed
model that fails loudly on malformed input. Pass plain, trusted values into the core.

Do not scatter validation models through the core, and do not validate data that our own
code already produced.

## Error handling

Let errors propagate. Do not catch an error just to return a null, an empty value, or a
sentinel: that silently converts a failure into a plausible-looking result and shifts an
invisible burden onto every caller.

Catch an error only when you can handle it at that point:
* retrying a transient failure
* translating a low-level error into a domain-specific one
* recovering with a meaningful fallback

When you do catch, be specific. Catching every error masks real bugs: unexpected errors
should fail loudly, not disappear.

## Logging

Log at system boundaries (HTTP handlers, queue consumers, scheduled job entry points), not
inside business logic. Logging is a side effect, and pure business functions have no reason
to log.

Do not log and swallow an error. Either propagate it and let the boundary log it once, or
handle it and log the outcome. Log meaningful events, not mechanical implementation steps.

## Documentation

Documentation comments are for public APIs only. Internal functions do not need them.

Comments are usually a code smell. If something needs a comment to be understood, rewrite it
to be self-explanatory through better names and structure: extract a named function or
predicate instead of explaining a condition. Never write comments that restate what the code
does.

## Naming

Avoid generic, meaningless names for modules, packages, classes, or directories: `utils`,
`common`, `helpers`, `shared`, `misc`. Use names that describe the specific responsibility
of the code, such as `timestamps`, `formatters`, `request_handler`, `retry_policy`.

The urge to create a `utils` module signals that the code needs to be reorganized into
focused, well-named modules.

## Paradigm

Prefer functional style over object-oriented, and object-oriented over imperative:
* small, pure, generic functions over classes with methods
* transforming data through function composition over mutating state
* expressions over statements where they stay readable

Do not over-engineer for paradigm purity. The best code is the simplest code that clearly
expresses intent: a plain loop or a simple class beats an unreadable pipeline.

Classes (or the language's equivalent) are the right tool when:
* **injecting behavior into business logic**: one interface with a clear name is easier to
  work with than several functions passed as arguments
* **keeping state over time**: accumulators, builders, stateful processors

A class that only wraps stateless logic should be a plain function.

## Testing

Business logic must be covered by unit tests. Because it is pure, it is tested by calling
functions with inputs and asserting outputs, with no mocks.

Minimize mocking and patching. Heavy mocking signals that side effects leaked into business
logic. Prefer black-box tests: assert on observable outputs and return values, not on
internal calls or implementation details.

For I/O and integration tests, prefer the framework's native test utilities (test clients,
in-memory servers) over wiring real clients by hand or mocking invocations.

## Cyclomatic complexity and function length

Keep functions short and straight. A function longer than ~20 lines signals that smaller,
named helpers should be extracted.

Do not add defensive checks for cases that cannot happen in the calling context. If no caller
passes null, do not guard against null. Unnecessary branches inflate complexity and suggest
to the reader that these cases are real.

Validate only at system boundaries: user input, external APIs, deserialization. Inside the
system, trust the contracts established by your own code.

## Types

Use the type system fully: declare types wherever the language allows it. Avoid runtime
type introspection (reflection, "has attribute" checks, type switches over unrelated types):
it signals that the types are not doing their job.

Do not overuse generic containers such as bare tuples or anonymous maps. When a function
returns or accepts several related values, introduce a named type. This documents the code
and prevents positional confusion at call sites.

Union types and "any" types are a code smell: a function that accepts or returns several
unrelated types is doing too much. Prefer specific, focused functions. Use them only where
a boundary imposes them.
