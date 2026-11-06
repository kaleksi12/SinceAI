# -*- coding: utf-8 -*-
"""Tiny JSON Schema subset validator (type, enum, const, required, properties,
additionalProperties, items, minimum, maximum, minItems, $ref to $defs), so the
package needs no third-party libraries. Enough for the schemas shipped here."""

_TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool, "null": type(None),
}


def _is(v, t):
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, _TYPES[t])


def validate(inst, schema, root=None, path="$"):
    root = root or schema
    errs = []
    if "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/$defs/"), ref
        return validate(inst, root["$defs"][ref.split("/")[-1]], root, path)
    t = schema.get("type")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not any(_is(inst, x) for x in ts):
            return ["%s: expected %s, got %s" % (path, t, type(inst).__name__)]
    if "enum" in schema and inst not in schema["enum"]:
        errs.append("%s: %r not in %s" % (path, inst, schema["enum"]))
    if "const" in schema and inst != schema["const"]:
        errs.append("%s: expected %r" % (path, schema["const"]))
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]:
            errs.append("%s: below minimum" % path)
        if "maximum" in schema and inst > schema["maximum"]:
            errs.append("%s: above maximum" % path)
    if isinstance(inst, dict):
        for k in schema.get("required", []):
            if k not in inst:
                errs.append("%s: missing required '%s'" % (path, k))
        props = schema.get("properties", {})
        for k, v in inst.items():
            if k in props:
                errs.extend(validate(v, props[k], root, "%s.%s" % (path, k)))
            elif schema.get("additionalProperties") is False:
                errs.append("%s: unexpected property '%s'" % (path, k))
            elif isinstance(schema.get("additionalProperties"), dict):
                errs.extend(validate(v, schema["additionalProperties"], root, "%s.%s" % (path, k)))
    if isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            errs.append("%s: fewer than %d items" % (path, schema["minItems"]))
        if "items" in schema:
            for i, v in enumerate(inst):
                errs.extend(validate(v, schema["items"], root, "%s[%d]" % (path, i)))
    return errs
