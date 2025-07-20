# grayhound_server/utils.py
import random
import math

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
        
    # 공백과 점을 모두 구분자로 사용하여 단어 분리
    words = []
    for part in name.split(' '):
        words.extend(part.split('.'))
    
    masked_words = [mask_word(word) for word in words if word]  # 빈 문자열 제외
    return ' '.join(masked_words)

def mask_name_for_guide(name: str) -> str:
    """Manual Cleanup Guide를 위해 35% 비율로 마스킹합니다."""
    if not isinstance(name, str) or not name:
        return name
    # 공백과 점을 모두 구분자로 사용하여 단어 분리
    words = []
    for part in name.split(' '):
        words.extend(part.split('.'))
    
    # 35% 비율로 마스킹하도록 ratio 전달
    masked_words = [mask_word(word, ratio=0.35) for word in words if word]  # 빈 문자열 제외
    return ' '.join(masked_words)

if __name__ == '__main__':
    test_names = ["nProtect Online Security", "AhnLab Safe Transaction", "Glary Utilities", "Defraggler", "INISAFE", "Delfino x86", "abc def.exe", "vzd"]
    for name in test_names:
        print(f'"{name}" -> "{mask_name(name)}"')
        print(f'"{name}" -> "{mask_name_for_guide(name)}"')