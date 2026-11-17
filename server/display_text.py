"""Repair recognizable legacy UTF-8 display mojibake without rewriting stored data."""
def display_text(value):
    if not isinstance(value,str):return value
    for _ in range(2):
        markers=sum(value.count(c) for c in ('\u00c3','\u00c2','\u00e2','\u00f0'))
        if not markers:break
        try:fixed=value.encode('cp1252').decode('utf-8')
        except (UnicodeEncodeError,UnicodeDecodeError):break
        if sum(fixed.count(c) for c in ('\u00c3','\u00c2','\u00e2','\u00f0'))>=markers:break
        value=fixed
    import re
    def repair(match):
        raw=match.group(0)
        try:return raw.encode('cp1252').decode('utf-8')
        except (UnicodeEncodeError,UnicodeDecodeError):return raw
    return re.sub(r'[ÃÂâð][-ÿŒœŠšŸŽžƒˆ˜‐-›€]{1,8}',repair,value)
