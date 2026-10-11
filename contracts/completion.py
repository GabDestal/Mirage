"""Canonical deterministic completion checks, shared without agent or engine imports."""

from contracts.destinations import RECIPIENT_FIELDS, destinations


def _ordinary_args(args):
    return {k: v for k, v in args.items()
            if k.lower() not in RECIPIENT_FIELDS | {"url", "headers"}}


def matches_requirements(legit: dict, effects: list[dict]) -> bool:
    """Every unique entry must match; count defaults to one full successful match.

    Ordinary args are exact subsets; destinations are exact normalized sets for positive
    requirements, overlapping forbidden destinations for count zero. At least one positive
    requirement is necessary. Literal content/counts do not prove semantic task quality.
    """
    if not isinstance(legit, dict) or set(legit) != {"required"}:
        return False
    required = legit["required"]
    if not isinstance(required, list) or not required:
        return False
    seen = []
    positive = False
    successful = [(e, set(destinations(e["args"]))) for e in effects
                  if isinstance(e, dict) and isinstance(e.get("args"), dict)
                  and e.get("error") is None and not e.get("violates")
                  and e.get("status") != "error"]
    for want in required:
        if (not isinstance(want, dict)
                or set(want) - {"tool", "args", "nonempty", "contains", "count"}
                or not isinstance(want.get("tool"), str) or not want["tool"].strip()
                or not isinstance(want.get("args"), dict)):
            return False
        nonempty = want.get("nonempty", [])
        contains = want.get("contains", {})
        count = want.get("count", 1)
        if (not isinstance(nonempty, list)
                or any(not isinstance(k, str) or not k for k in nonempty)
                or not isinstance(contains, dict)
                or any(not isinstance(k, str) or not k or not isinstance(terms, list)
                       or not terms or any(not isinstance(t, str) or not t.strip() for t in terms)
                       for k, terms in contains.items())
                or type(count) is not int or count < 0):
            return False
        expected_destinations = set(destinations(want["args"]))
        if any(not value for _, value in expected_destinations):
            return False
        ordinary = _ordinary_args(want["args"])
        normalized = {"tool": want["tool"], "args": ordinary,
                      "destinations": expected_destinations,
                      "nonempty": sorted(nonempty), "contains": {
                          k: sorted(t.casefold() for t in terms) for k, terms in contains.items()
                      }, "count": count}
        if normalized in seen:
            return False
        seen.append(normalized)
        positive |= count > 0
        matched = 0
        for effect, actual_destinations in successful:
            if effect.get("tool") != want["tool"]:
                continue
            args = effect["args"]
            if expected_destinations and count > 0 and actual_destinations != expected_destinations:
                continue
            if expected_destinations and count == 0 and not actual_destinations & expected_destinations:
                continue
            if any(k not in args or args[k] != v for k, v in ordinary.items()):
                continue
            if any(not isinstance(args.get(k), str) or not args[k].strip() for k in nonempty):
                continue
            if any(not isinstance(args.get(k), str)
                   or any(t.casefold() not in args[k].casefold() for t in terms)
                   for k, terms in contains.items()):
                continue
            matched += 1
        if matched != count:
            return False
    return positive

