# grayhound_server/utils.py
import random

def mask_name(name: str) -> str:
    """
    프로그램 이름의 첫 글자와 마지막 글자를 제외한 나머지 부분의
    약 40%를 무작위로 '*'로 마스킹합니다.
    예: "nProtect Online Security" -> "nProt**t Onl**e Secu***y"
    """
    if not isinstance(name, str) or len(name) <= 2:
        return name

    first_char = name[0]
    last_char = name[-1]
    middle = name[1:-1]
    
    if not middle:
        return name

    middle_chars = list(middle)
    middle_len = len(middle_chars)
    
    # 마스킹할 인덱스 개수 계산 (중간 부분의 40%)
    # 공백이 아닌 문자만 마스킹 대상으로 고려
    non_space_indices = [i for i, char in enumerate(middle_chars) if char != ' ']
    mask_count = int(len(non_space_indices) * 0.4)
    
    if mask_count == 0 and middle_len > 0:
        # 마스킹할 글자가 너무 적으면 최소 1개는 마스킹
        mask_count = 1

    # 마스킹할 인덱스를 무작위로 선택
    indices_to_mask = random.sample(non_space_indices, k=mask_count)
    
    # 선택된 인덱스의 문자를 '*'로 변경
    for i in indices_to_mask:
        middle_chars[i] = '*'
            
    return first_char + "".join(middle_chars) + last_char

if __name__ == '__main__':
    test_names = ["nProtect Online Security", "AhnLab Safe Transaction", "Glary Utilities", "Defraggler", "INISAFE", "vzd"]
    for name in test_names:
        print(f'"{name}" -> "{mask_name(name)}"')