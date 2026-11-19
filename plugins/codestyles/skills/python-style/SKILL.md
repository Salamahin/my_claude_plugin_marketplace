---
name: python-style
description: Python coding style guide — builds on generic-style and adds Python idioms and examples: frozen dataclasses, mutable default arguments, Pydantic at the boundary, exceptions, type hints, pytest without MagicMock/patch, native test clients. Use whenever writing, editing, or reviewing Python code.
---

# Python coding style

**This guide builds on `codestyles:generic-style`. Read and apply that skill first.** It holds
the rules and their rationale; this skill shows them in Python and adds Python-only rules.
When the two disagree, this skill wins for Python code.

The sections below follow the order of `generic-style`.

## Separate side effects from business logic

Python's usual entropy sources are `datetime.now()`, `time.time()`, `random` and `uuid4()`.
Capture them at the boundary and inject them as values.

**Bad example**: mixing file I/O with business logic
```python
def calc_statistics(filename: str) -> float:
    with open(filename, "r") as file:
        data = json.load(file)
    return average(row["value"] for row in data)
```

**Good example**: business logic operates only on data
```python
def calc_statistics(data: list[dict]) -> float:
    return average(row["value"] for row in data)
```

**Boundary example**: I/O happens outside the business function
```python
def calc_statistics_from_file(filename: str) -> float:
    with open(filename, "r") as file:
        data = json.load(file)
    return calc_statistics(data)
```

**Bad example**: business logic depends on hidden entropy
```python
def pick_discount() -> int:
    current_second = datetime.now(UTC).second
    draw = Random().random()

    if current_second % 2 == 0 and draw > 0.5:
        return 20
    if draw > 0.2:
        return 10
    return 0
```

**Good example**: entropy is captured outside and injected explicitly
```python
@dataclass(frozen=True)
class DiscountEntropy:
    current_second: int
    draw: float

def pick_discount(entropy: DiscountEntropy) -> int:
    if entropy.current_second % 2 == 0 and entropy.draw > 0.5:
        return 20
    if entropy.draw > 0.2:
        return 10
    return 0
```

**Boundary example**: entropy is collected outside the business function
```python
def make_discount_entropy(rng: Random) -> DiscountEntropy:
    return DiscountEntropy(
        current_second=datetime.now(UTC).second,
        draw=rng.random(),
    )

def pick_discount_live(rng: Random) -> int:
    return pick_discount(entropy=make_discount_entropy(rng))
```

## Prefer non-nullable inputs in business logic

In Python, "nullable" means `X | None` (or `Optional[X]`).

**Bad example**: a nullable input where an empty collection already models the neutral case
```python
def foo(args: list[str] | None):
    if args is None:
        return

    for item in args:
        yield item
```

**Good example**: using the collection's natural empty-state behavior
```python
def foo(args: list[str]):
    for item in args:
        yield item
```

**Boundary normalization example**:
```python
def foo_from_payload(args: list[str] | None):
    return foo(args or [])
```

## Prefer immutable data

Use `@dataclass(frozen=True)` for value objects. Prefer tuples and `frozenset` over lists
and sets when a collection does not need to change.

The mutable default argument is Python's classic trap: the default is evaluated once at
definition time and shared across all calls.

**Bad example**: mutating a passed-in argument
```python
def add_tag(tags: list[str], tag: str) -> None:
    tags.append(tag)
```

**Good example**: return a new value
```python
def add_tag(tags: list[str], tag: str) -> list[str]:
    return [*tags, tag]
```

**Bad example**: mutable default argument accumulates state across calls
```python
def collect(item: str, result: list[str] = []) -> list[str]:
    result.append(item)
    return result
```

**Good example**: use an immutable default
```python
def collect(item: str, result: tuple[str, ...] = ()) -> tuple[str, ...]:
    return (*result, item)
```

## Validate untrusted data at the boundary

`@dataclass(frozen=True)` is the default for internal value objects, but it does not
validate: it trusts whatever it is given. For data crossing the system boundary, prefer a
**Pydantic** model when validation adds value. It parses and validates at the edge, coerces
types, and fails loudly on malformed input.

Keep Pydantic at the boundary only. Do not reach for it when a frozen dataclass over
already-trusted internal data is enough.

**Bad example**: trusting an untyped external payload deep in the code
```python
def total_price(payload: dict) -> float:
    return sum(item["price"] * item["qty"] for item in payload["items"])
```

**Good example**: validate at the boundary, then work with trusted data
```python
class LineItem(BaseModel):
    price: float
    qty: int

class Order(BaseModel):
    items: list[LineItem]

def total_price(order: Order) -> float:
    return sum(item.price * item.qty for item in order.items)

# boundary: parse + validate untrusted input once
order = Order.model_validate(raw_payload)
```

## Error handling

In Python, errors are exceptions. Never write `except Exception:` (or a bare `except:`) to
return a default. Chain translated exceptions with `raise ... from e` so the cause survives.

**Bad example**: swallowing the exception and returning `None`
```python
def load_config(path: str) -> Config | None:
    try:
        with open(path) as f:
            return Config(**json.load(f))
    except Exception:
        return None
```

**Good example**: let the exception propagate — the caller knows what to do
```python
def load_config(path: str) -> Config:
    with open(path) as f:
        return Config(**json.load(f))
```

**Boundary example**: translate a low-level exception into a domain one at the edge
```python
def load_config(path: str) -> Config:
    try:
        with open(path) as f:
            return Config(**json.load(f))
    except FileNotFoundError as e:
        raise ConfigNotFoundError(path) from e
```

**Bad example**: catching too broadly masks unexpected failures
```python
try:
    result = process(data)
except Exception:
    return default_result
```

**Good example**: catch only what you expect and can handle
```python
try:
    result = process(data)
except ValueError as e:
    raise InvalidDataError(data) from e
```

## Logging

Use the standard `logging` module with lazy `%`-style arguments, not f-strings, so messages
are only formatted when emitted.

**Bad example**: logging and swallowing — the error disappears
```python
def get_user(user_id: str) -> User | None:
    try:
        return db.fetch_user(user_id)
    except UserNotFoundError as e:
        logger.error("Failed to fetch user: %s", e)
        return None
```

**Good example**: propagate the exception; log once at the boundary
```python
# business logic — no logging
def get_user(user_id: str) -> User:
    return db.fetch_user(user_id)

# boundary (e.g. HTTP handler)
try:
    user = get_user(user_id)
except UserNotFoundError:
    logger.warning("User not found: %s", user_id)
    return Response(status=404)
```

**Bad example**: logging mechanical steps adds noise without signal
```python
def process_order(order: Order) -> Receipt:
    logger.info("Processing order %s", order.id)
    receipt = compute_receipt(order)
    logger.info("Order %s processed", order.id)
    return receipt
```

**Good example**: log meaningful events at the boundary
```python
def process_order(order: Order) -> Receipt:
    return compute_receipt(order)

logger.info("Order %s fulfilled, total=%.2f", order.id, receipt.total)
```

## Documentation

Docstrings are for public APIs only. Internal functions and methods do not need them.

**Bad example**: comment restates the code
```python
# Read the file
with open(path) as f:
    data = f.read()
```

**Good example**: the code speaks for itself
```python
raw_config = path.read_text()
```

**Bad example**: comment compensates for unclear logic
```python
# Retry only on transient errors
if error.code in (429, 503):
    retry()
```

**Good example**: extract a named predicate
```python
def is_transient(error: HttpError) -> bool:
    return error.code in (429, 503)

if is_transient(error):
    retry()
```

## Naming

**Bad examples**: `utils.py`, `common/`, `helpers.py`, `shared/`, `misc.py`

**Good examples**: `timestamps.py`, `formatters.py`, `request_handler.py`, `retry_policy.py`

## Paradigm

Comprehensions and generator expressions are Python's idiomatic functional style; prefer
them over manual accumulation loops.

**Bad example**: imperative accumulation
```python
def active_emails(users: list[User]) -> list[str]:
    result = []
    for user in users:
        if user.is_active:
            result.append(user.email)
    return result
```

**Good example**: functional, concise, self-explanatory
```python
def active_emails(users: list[User]) -> list[str]:
    return [u.email for u in users if u.is_active]
```

**Bad example**: passing multiple functions to inject behavior
```python
def process_order(order: Order, fetch: Callable, save: Callable, notify: Callable):
    data = fetch(order.id)
    result = compute(data)
    save(result)
    notify(result)
```

**Good example**: a class groups the injected behavior under a meaningful interface
```python
class OrderProcessor:
    def __init__(self, repo: OrderRepository, notifier: Notifier):
        self._repo = repo
        self._notifier = notifier

    def process(self, order: Order) -> None:
        data = self._repo.fetch(order.id)
        result = compute(data)
        self._repo.save(result)
        self._notifier.notify(result)
```

**Bad example**: class wrapping stateless logic that needs no encapsulation
```python
class DiscountCalculator:
    def __init__(self, rate: float):
        self.rate = rate

    def apply(self, price: float) -> float:
        return price * (1 - self.rate)
```

**Good example**: a plain function is sufficient
```python
def apply_discount(price: float, rate: float) -> float:
    return price * (1 - rate)
```

## Testing

Use pytest. Minimize `MagicMock`, `patch` and `monkeypatch`: in Python they are the usual
sign that side effects leaked into business logic. For web frameworks, use the native test
client (for example FastAPI/Starlette `TestClient`).

**Bad example**: mocking internals to test business logic
```python
def test_discount():
    with patch("myapp.discount.datetime") as mock_dt:
        mock_dt.now.return_value.second = 4
        with patch("myapp.discount.Random") as mock_rng:
            mock_rng.return_value.random.return_value = 0.9
            assert pick_discount() == 20
```

**Good example**: business logic is pure — just pass the inputs
```python
def test_discount():
    entropy = DiscountEntropy(current_second=4, draw=0.9)
    assert pick_discount(entropy) == 20
```

**Bad example**: testing an HTTP endpoint by calling `requests` or mocking the handler
```python
def test_create_order():
    with patch("myapp.routes.save_order") as mock_save:
        mock_save.return_value = None
        response = requests.post("http://localhost:8000/orders", json={...})
        assert response.status_code == 201
        mock_save.assert_called_once()
```

**Good example**: use the framework's native test client
```python
def test_create_order(client: TestClient):
    response = client.post("/orders", json={...})
    assert response.status_code == 201
```

## Cyclomatic complexity and function length

**Bad example**: defensive checks that cannot be triggered by any real caller
```python
def apply_discount(price: float, rate: float) -> float:
    if price is None:
        raise ValueError("price must not be None")
    if rate is None:
        raise ValueError("rate must not be None")
    if rate < 0 or rate > 1:
        raise ValueError("rate must be between 0 and 1")
    return price * (1 - rate)
```

**Good example**: trust the caller, just do the work
```python
def apply_discount(price: float, rate: float) -> float:
    return price * (1 - rate)
```

**Bad example**: one large function doing too much
```python
def process_order(order: Order) -> Receipt:
    # validate
    if not order.items:
        raise ValueError("empty order")
    # apply discounts
    total = sum(item.price for item in order.items)
    if order.coupon:
        total *= (1 - order.coupon.rate)
    # compute tax
    tax = total * 0.2
    total_with_tax = total + tax
    # build receipt
    lines = [f"{item.name}: {item.price}" for item in order.items]
    return Receipt(lines=lines, total=total_with_tax)
```

**Good example**: extract focused helpers
```python
def process_order(order: Order) -> Receipt:
    total = apply_coupon(subtotal(order.items), order.coupon)
    return build_receipt(order.items, with_tax(total))
```

## Types

Always use type hints. Avoid `hasattr`, `getattr`, `isinstance` checks and other runtime type
introspection. Union types (`X | Y`) and `Any` are a code smell outside boundaries imposed by
an API or framework.

**Bad example**: anonymous tuple hides meaning
```python
def get_coordinates() -> tuple[float, float]:
    return 51.5, 0.1
```

**Good example**: a named type makes intent explicit
```python
@dataclass(frozen=True)
class Point:
    x: float
    y: float

def get_coordinates() -> Point:
    return Point(x=51.5, y=0.1)
```

**Bad example**: one function handling multiple unrelated types
```python
def render(value: dict | list | str) -> str:
    ...
```

**Good example**: separate, focused functions with precise types
```python
def render_dict(value: dict) -> str: ...
def render_list(value: list) -> str: ...
def render_str(value: str) -> str: ...
```
