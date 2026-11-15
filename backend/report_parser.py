"""Conservative bilingual report structuring with exact source spans.

This is deterministic local extraction, not an autonomous radiology interpreter.
Every clause and measurement is preserved; ambiguity always requires review.
No report text is ever sent to an image model or a remote language service.
"""
import re
from uuid import uuid4

KINDS = {
    'nodule': r'결절|\bnodules?\b',
    'pleural_effusion': r'흉수|흉막\s*삼출|\bpleural\s+effusions?\b',
    'pericardial_effusion': r'심낭\s*(?:삼출|액)|\bpericardial\s+effusions?\b',
}
LOCATION_PATTERNS = {
    'RUL': r'\bRUL\b|right upper lobe|우(?:측|폐)?\s*상엽|오른쪽\s*위폐엽',
    'RML': r'\bRML\b|right middle lobe|우(?:측|폐)?\s*중엽|오른쪽\s*중간폐엽',
    'RLL': r'\bRLL\b|right lower lobe|우(?:측|폐)?\s*하엽|오른쪽\s*아래폐엽',
    'LUL': r'\bLUL\b|left upper lobe|좌(?:측|폐)?\s*상엽|왼쪽\s*위폐엽',
    'LLL': r'\bLLL\b|left lower lobe|좌(?:측|폐)?\s*하엽|왼쪽\s*아래폐엽',
}
MEASUREMENT = re.compile(r'(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm\^?3|mm³|cm\^?3|cm³|ml\b|mL\b|㎖|mm\b|cm\b|㎜|㎝)', re.I)


def extract_report(text):
    """Return one supported finding per kind per source clause, plus unparsed clauses.

    Spans use Unicode codepoint offsets, not UTF-16 code units. Multi-lesion
    clauses retain all numbers/locations and are explicitly ambiguous instead
    of inventing a lesion-to-measurement alignment.
    """
    boundaries = [0]
    for match in re.finditer(r'\n|;|,(?!\d)|(?<=[.!?。])\s+|\bbut\b|하지만|(?<=없고)\s+|(?=\bwithout\b)', text, re.I):
        boundaries.extend([match.start(), match.end()])
    boundaries.append(len(text))
    boundaries = sorted(set(boundaries))
    items = []
    for low, high in zip(boundaries, boundaries[1:]):
        raw = text[low:high]
        start = low + len(raw) - len(raw.lstrip())
        end = high - (len(raw) - len(raw.rstrip()))
        quote = text[start:end]
        if not quote.strip(' ,;\n') or re.fullmatch(r'but|하지만', quote, re.I):
            continue
        kinds = [kind for kind, pattern in KINDS.items() if re.search(pattern, quote, re.I)] or ['other']
        locations = [name for name, pattern in LOCATION_PATTERNS.items() if re.search(pattern, quote, re.I)]
        # Stability wording is about change, not absence of the lesion itself.
        presence_text = re.sub(r'no (?:significant )?(?:interval )?change|변화\s*(?:없음|없다|없)', '', quote, flags=re.I)
        uncertain = bool(re.search(r'cannot exclude|can.?t exclude|배제.{0,8}(?:없|못)|의심|가능성|suspect|possible|indeterminate|\brule out\b|\br/o\b', quote, re.I))
        negative = bool(re.search(r'\bno\b|\bwithout\b|not (?:seen|identified)|관찰되지|보이지\s*않|없(?:음|다|고|습니다)?', presence_text, re.I))
        presence = 'uncertain' if uncertain else 'absent' if negative else 'mentioned'
        temporal = 'comparison' if re.search(r'compared|이전.{0,20}(?:대비|비교)|증가|감소|unchanged|stable|변화\s*없|\bfrom\b', quote, re.I) else 'prior' if re.search(r'previous|prior|과거|이전|작년', quote, re.I) else 'current'
        measurements = []
        for match in MEASUREMENT.finditer(quote):
            unit = match['unit'].lower().replace('^', '').replace('³', '3').replace('㎜', 'mm').replace('㎝', 'cm').replace('㎖', 'ml')
            dimension = 'volume' if unit in {'ml', 'mm3', 'cm3'} else 'length'
            factor = 1000 if unit in {'ml', 'cm3'} else 10 if unit == 'cm' else 1
            measurements.append({'value': float(match['value']), 'unit': match['unit'],
                                 'normalized_value': float(match['value']) * factor,
                                 'normalized_unit': 'mm3' if dimension == 'volume' else 'mm',
                                 'dimension': dimension, 'source_start': start + match.start(), 'source_end': start + match.end(),
                                 'temporal_context': temporal})
        for kind in kinds:
            repeated = len(re.findall(KINDS.get(kind, r'(?!)'), quote, re.I)) > 1
            items.append({'id': str(uuid4()), 'kind': kind, 'locations': locations,
                          'presence': presence, 'temporal_context': temporal, 'measurements': measurements,
                          'followup_text': quote if re.search(r'follow.?up|추적|재검|권고|recommend', quote, re.I) else None,
                          'source_span': {'start': start, 'end': end, 'text': quote},
                          'ambiguous': len(locations) > 1 or len(kinds) > 1 or repeated,
                          'needs_review': True, 'confirmation': 'unconfirmed', 'excluded': False,
                          'user_note': '', 'origin': 'local_rule_extraction'})
    return items


def validate_items(items, report_text):
    """Reject forged source quotes and invalid unit/enum data before versioning."""
    if not isinstance(items, list) or len(items) > 1000:
        raise ValueError('구조화 항목은 최대 1000개입니다.')
    ids = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or item['id'] in ids:
            raise ValueError('항목 식별자가 없거나 중복되었습니다.')
        ids.add(item['id'])
        if item.get('kind') not in {*KINDS, 'other'} or item.get('presence') not in {'mentioned', 'absent', 'uncertain'}:
            raise ValueError('종류 또는 부정/의심 상태가 유효하지 않습니다.')
        if item.get('temporal_context') not in {'current', 'prior', 'comparison', 'unknown'}:
            raise ValueError('시간 맥락이 유효하지 않습니다.')
        if item.get('confirmation') not in {'unconfirmed', 'confirmed'} or type(item.get('excluded')) is not bool:
            raise ValueError('확인/제외 상태가 유효하지 않습니다.')
        if not isinstance(item.get('locations'), list) or not all(x in LOCATION_PATTERNS or x in {'left','right','unknown'} for x in item['locations']):
            raise ValueError('위치가 유효하지 않습니다.')
        span = item.get('source_span')
        if span is not None:
            a, b = span.get('start'), span.get('end')
            if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(report_text) or report_text[a:b] != span.get('text'):
                raise ValueError('원문 범위/인용이 일치하지 않습니다.')
        elif item.get('origin') != 'user_added':
            raise ValueError('원문 출처 없는 추가 항목은 사용자 해석으로 구별해야 합니다.')
        for measurement in item.get('measurements', []):
            import math
            if measurement.get('dimension') not in {'length','volume'} or measurement.get('normalized_unit') != {'length':'mm','volume':'mm3'}.get(measurement.get('dimension')) or type(measurement.get('normalized_value')) not in {int,float} or not math.isfinite(measurement['normalized_value']) or measurement['normalized_value'] < 0:
                raise ValueError('측정값과 단위가 유효하지 않습니다.')
    return items
