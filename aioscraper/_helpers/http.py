def get_encoding(content_type: str) -> str:
    parts = content_type.split(";")
    params = parts[1:]
    items_to_strip = "\"' "

    for param in params:
        param = param.strip()
        if not param:
            continue

        if "=" not in param:
            continue

        key, value = param.split("=", 1)
        key = key.strip(items_to_strip).lower()
        value = value.strip(items_to_strip)

        if key == "charset":
            try:
                "".encode(value)
                return value
            except LookupError:
                return "utf-8"

    return "utf-8"
