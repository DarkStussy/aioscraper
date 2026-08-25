from typing import Iterable

# passed positionally at the call site, so cb_kwargs cannot carry them either
CALLBACK_ARGUMENTS = frozenset({"request", "response", "exc"})
# injected from the dependency map; config is missing on purpose, it is documented as overridable
RESERVED_DEPENDENCIES = CALLBACK_ARGUMENTS | {"schedule_request", "send_request", "pipeline"}


def reject_reserved(names: Iterable[str], reserved: frozenset[str], label: str):
    taken = sorted(reserved.intersection(names))
    if taken:
        raise ValueError(f"{label} reserved by the framework: {', '.join(taken)}")
