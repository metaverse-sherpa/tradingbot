def reconstruct_pem(flat_key):
    # A flat key looks like: -----BEGIN EC PRIVATE KEY-----MHQCAQEEI...-----END EC PRIVATE KEY-----
    if "-----BEGIN" in flat_key and "-----END" in flat_key and "\n" not in flat_key:
        # Find the start and end markers
        import re
        match = re.match(r'(-----BEGIN.*?-----)(.*?)(-----END.*?-----)', flat_key)
        if match:
            header, body, footer = match.groups()
            body = body.replace(" ", "")
            # Wrap body every 64 chars
            wrapped_body = "\n".join([body[i:i+64] for i in range(0, len(body), 64)])
            return f"{header}\n{wrapped_body}\n{footer}"
    return flat_key

print(reconstruct_pem("-----BEGIN EC PRIVATE KEY-----MHQCAQEEIABCDEFG1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ-----END EC PRIVATE KEY-----"))
