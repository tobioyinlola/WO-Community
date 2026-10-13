"""A small JSON patch (RFC 6902 subset): add, remove, replace and move.

Used wherever a structured document is edited by operations: decks and prototypes. Operations
apply to a copy, all or nothing, and only under the top level keys the caller names.
"""

import copy
from typing import Any


class PatchError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _walk(doc: Any, parts: list[str]) -> tuple[Any, str]:
    node = doc
    for part in parts[:-1]:
        node = _step(node, part)
    return node, parts[-1]


def _step(node: Any, part: str) -> Any:
    if isinstance(node, list):
        if not part.isdigit() or int(part) >= len(node):
            raise PatchError(f"No item {part}.")
        return node[int(part)]
    if isinstance(node, dict):
        if part not in node:
            raise PatchError(f"No {part}.")
        return node[part]
    raise PatchError(f"Cannot go into {part}.")


def _split(path: Any, roots: tuple[str, ...]) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        raise PatchError("A path starts with a slash.")
    parts = [p.replace("~1", "/").replace("~0", "~") for p in path.split("/")[1:]]
    if not parts or parts[0] not in roots:
        raise PatchError("Only " + ", ".join("/" + r for r in roots) + " can be changed.")
    return parts


def apply(content: dict[str, Any], ops: Any, *, roots: tuple[str, ...]) -> dict[str, Any]:
    """Apply add, remove, replace and move operations to a copy of the content.

    Only paths under the named top level keys may be touched.
    """
    if not isinstance(ops, list) or not 1 <= len(ops) <= 200:
        raise PatchError("Send between 1 and 200 operations.")
    doc = copy.deepcopy(content)
    for op in ops:
        if not isinstance(op, dict) or op.get("op") not in ("add", "remove", "replace", "move"):
            raise PatchError("Each operation is add, remove, replace or move.")
        kind = op["op"]
        parts = _split(op.get("path"), roots)
        if kind == "move":
            source = _split(op.get("from"), roots)
            holder, key = _walk(doc, source)
            value = _step(holder, key)
            if isinstance(holder, list):
                holder.pop(int(key))
            else:
                del holder[key]
            kind, payload = "add", value
        else:
            payload = op.get("value")
        holder, key = _walk(doc, parts)
        if kind == "remove":
            if isinstance(holder, list) and key.isdigit() and int(key) < len(holder):
                holder.pop(int(key))
            elif isinstance(holder, dict) and key in holder:
                del holder[key]
            else:
                raise PatchError("Nothing to remove there.")
        elif kind == "replace":
            if isinstance(holder, list) and key.isdigit() and int(key) < len(holder):
                holder[int(key)] = payload
            elif isinstance(holder, dict) and key in holder:
                holder[key] = payload
            else:
                raise PatchError("Nothing to replace there.")
        else:  # add
            if isinstance(holder, list):
                if key == "-":
                    holder.append(payload)
                elif key.isdigit() and int(key) <= len(holder):
                    holder.insert(int(key), payload)
                else:
                    raise PatchError("Bad position.")
            elif isinstance(holder, dict):
                holder[key] = payload
            else:
                raise PatchError("Cannot add there.")
    return doc
