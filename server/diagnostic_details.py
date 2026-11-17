"""Safe analysis shape diagnostics: bounded numbers and fixed enums only."""
INTEGER_BOUNDS={'candidateScore':(0,100),'scoreThreshold':(0,100),'minClipSeconds':(15,60),'maxClipSeconds':(15,60),'candidateMillis':(15000,60000),'responseChars':(0,1000000),'textBlocks':(0,1000),'parsePosition':(0,1000000),'parseLine':(1,1000000),'parseColumn':(1,1000000)}
ENUMS={'monitorState':frozenset({'connecting','monitoring','reconnecting'}),'chatStatus':frozenset({'connecting','connected','unavailable','disabled'}),'speechStatus':frozenset({'active','waiting','unavailable','disabled'}),'stopReason':frozenset({'end_turn','max_tokens','stop_sequence','tool_use','pause_turn','refusal','other'}),'outputShape':frozenset({'empty','fenced','plain'}),'failureReason':frozenset({'json_decode','ambiguous_json','duplicate_key','candidate_schema','timestamp_type','timestamp_bounds','clip_length','score','metadata_title','metadata_caption','metadata_rationale','stop_reason','response_size','unexpected_content'})}
INTEGER_BOUNDS.update(httpStatus=(400,599),returnedClipMillis=(0,305000))

def validate_diagnostic_details(details):
    if not isinstance(details,dict) or set(details)-set(INTEGER_BOUNDS)-set(ENUMS)-{'companionVersion'}:raise ValueError('Invalid diagnostic details.')
    for key,value in details.items():
        if key=='companionVersion':
            import re
            if not isinstance(value,str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-beta)?',value):raise ValueError('Invalid diagnostic version.')
        elif key in INTEGER_BOUNDS:
            low,high=INTEGER_BOUNDS[key]
            if type(value) is not int or not low<=value<=high:raise ValueError('Invalid diagnostic number.')
        elif not isinstance(value,str) or value not in ENUMS[key]:raise ValueError('Invalid diagnostic enum.')
    return dict(details)
