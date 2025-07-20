# grayhound_server/utils.py
import random
import math
import re

def mask_word(word: str, ratio: float = 0.5) -> str:
    """
    단어의 첫 글자와 마지막 글자를 제외한 나머지 부분의
    지정된 비율만큼 '*'로 마스킹
    예:"nPro***t Onl*** Secu****"
    """
    if len(word) <= 2:
        return word

    first_char = word[0]
    last_char = word[-1]
    middle = list(word[1:-1])
        
    # 마스킹할 글자 수 계산 (단어 전체 길이 기준)
    mask_count = math.floor(len(word) * ratio)
    
    # 실제 마스킹 가능한 글자 수는 중간 부분의 길이
    possible_mask_len = len(middle)
    
    # 마스킹할 글자 수가 마스킹 가능한 글자 수보다 많으면 조정
    if mask_count > possible_mask_len:
        mask_count = possible_mask_len
         
    # 마스킹할 인덱스를 무작위로 선택
    indices_to_mask = random.sample(range(possible_mask_len), k=mask_count)
    
    # 선택된 인덱스의 문자를 '*'로 변경
    for i in indices_to_mask:
        middle[i] = '*'
            
    return first_char + "".join(middle) + last_char

def mask_name(name: str) -> str:
    """
    프로그램 이름(문자열)을 단어 단위로 분리하여,
    각 단어에 mask_word 함수를 적용한 후 다시 합침.
    """
    if not isinstance(name, str) or not name:
        return name
        
    # Split by delimiters but keep them in the list to preserve the original structure
    parts = re.split(r'([ .()])', name)
    masked_parts = [mask_word(part) if part.isalnum() else part for part in parts if part]
    return "".join(masked_parts)

def mask_name_for_guide(name: str) -> str:
    """Manual Cleanup Guide를 위해 35% 비율로 마스킹합니다."""
    if not isinstance(name, str) or not name:
        return name
    # 공백과 점을 모두 구분자로 사용하여 단어 분리
    # 35% 비율로 마스킹하도록 ratio 전달
    parts = re.split(r'([ .()])', name)
    masked_parts = [mask_word(part, ratio=0.35) if part.isalnum() else part for part in parts if part]
    return "".join(masked_parts)

def enhanced_mask_name(full_name: str, generic_name: str) -> str:
    """
    full_name에서 generic_name을 찾아 마스킹하고, 나머지 부분은 기존 mask_name 함수를 사용하여 마스킹합니다.
    """
    if not all([isinstance(full_name, str), full_name, isinstance(generic_name, str), generic_name]):
        return mask_name(full_name)  # Fallback to the original function

    try:
        # Find the generic_name within the full_name (case-insensitive)
        match = re.search(re.escape(generic_name), full_name, re.IGNORECASE)
        
        if not match:
            return mask_name(full_name) # If not found, use the default masking

        start, end = match.span()
        matched_generic_part = full_name[start:end]
        
        # Mask the found generic part more aggressively
        masked_generic = mask_word(matched_generic_part, ratio=0.8) 
        
        # Mask the prefix and suffix parts separately
        prefix = full_name[:start]
        suffix = full_name[end:]
        
        masked_prefix = mask_name(prefix)
        masked_suffix = mask_name(suffix)

        return masked_prefix + masked_generic + masked_suffix

    except Exception:
        # Fallback safely in case of any regex or other errors
        return mask_name(full_name)

if __name__ == '__main__':
    test_names = ["nProtect Online Security", "AhnLab Safe Transaction", "Glary Utilities", "Defraggler", "INISAFE", "Delfino x86", "abc def.exe", "THEABCDEFGSAFE.exe" "vzd"]
    for name in test_names:
        print(f'"{name}" -> "{mask_name(name)}"')
        print(f'"{name}" -> "{mask_name_for_guide(name)}"')