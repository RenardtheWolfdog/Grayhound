# Grayhound_CLI.py
# Grayhound Standalone Server & Command-Line Interface

import asyncio
import logging
from SecurityAgentManager import SecurityAgentManager
from secure_agent.ThreatIntelligenceCollector import ThreatIntelligenceCollector
import pandas as pd
import database
import pprint # 쿼리 목록 예쁘게 출력하기 위해

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
)

def print_banner():
    """그래피티 아트 스타일의 Grayhound 배너"""
    print("\n" + "█"*70)
    print("""
    ░██████╗░██████╗░░█████╗░██╗░░░██╗██╗░░██╗░█████╗░██╗░░░██╗███╗░░██╗██████╗░
    ██╔════╝░██╔══██╗██╔══██╗╚██╗░██╔╝██║░░██║██╔══██╗██║░░░██║████╗░██║██╔══██╗
    ██║░░██╗░██████╔╝███████║░╚████╔╝░███████║██║░░██║██║░░░██║██╔██╗██║██║░░██║
    ██║░░╚██╗██╔══██╗██╔══██║░░╚██╔╝░░██╔══██║██║░░██║██║░░░██║██║╚████║██║░░██║
    ╚██████╔╝██║░░██║██║░░██║░░░██║░░░██║░░██║╚█████╔╝╚██████╔╝██║░╚███║██████╔╝
    ░╚═════╝░╚═╝░░╚═╝╚═╝░░╚═╝░░░╚═╝░░░╚═╝░░╚═╝░╚════╝░░╚═════╝░╚═╝░░╚══╝╚═════╝░
    """)
    print("    🎯 AI-Powered Bloatware Hunter | 블로트웨어 스나이퍼 v1.0")
    print("    💀 NO MERCY FOR JUNK | 블로트웨어 제거 전문가")
    print("█"*70 + "\n")
    
async def update_db_workflow(collector):
    """DB 업데이트를 위한 사용자 입력 및 AI 쿼리 생성 워크플로우"""
    print("\n[ 🕵️ AI 기반 DB 업데이트 ]")
    country = input("대상 국가를 입력하세요 (예: South Korea, USA): ").strip()
    os_type = input("대상 운영체제를 입력하세요 (예: Windows 11, macOS Sonoma): ").strip()

    if not country or not os_type:
        print("❌ 국가와 운영체제는 필수 입력 항목입니다. 메뉴로 돌아갑니다.")
        return

    print("\n⏳ AI가 입력된 정보를 기반으로 최적화된 검색 쿼리를 생성합니다...")
    dynamic_queries = await collector.generate_dynamic_queries(country, os_type)

    if not dynamic_queries:
        print("❌ 쿼리 생성에 실패했습니다. 입력 값을 확인하거나 잠시 후 다시 시도해주세요.")
        return

    print("\n✅ AI가 아래와 같이 검색 쿼리를 생성했습니다.")
    print("-" * 50)
    pprint.pprint(dynamic_queries)
    print("-" * 50)
    print("\n⚠️ 경고: 이 쿼리는 AI가 생성한 결과이므로 정확하지 않을 수 있습니다.")
    print("만일 쿼리가 부적절하다고 판단된다면 'n'를 입력하여 취소하세요.")
    print("프로그램 오남용으로 인한 모든 책임은 사용자 본인에게 있습니다.")

    proceed = input("\n이 쿼리를 사용하여 DB 업데이트를 진행하시겠습니까? (y/n) > ").strip().lower()

    if proceed == 'y':
        print("\n⏳ DB 업데이트를 시작합니다. 다소 시간이 걸릴 수 있습니다...")
        try:
            await collector.run_all_collectors(dynamic_queries)
            db_count = await database.get_threat_count()
            print(f"\n✅ DB 업데이트 완료! 현재 {db_count}개의 위협 정보가 저장되었습니다.")
        except Exception as e:
            logging.error(f"DB 업데이트 중 오류 발생: {e}", exc_info=True)
            print("\n❌ DB 업데이트에 실패했습니다. 로그를 확인해주세요.")
    else:
        print("\n⏩ 작업을 취소하고 메인 메뉴로 돌아갑니다.")

async def main_cli():
    """Grayhound 독립 실행을 위한 Command-Line Interface"""
    print_banner()
    
    # SecurityAgentManager 초기화 (우선 프로토타입에서는 세션 ID는 CLI용으로 고정, 사용자 이름은 'user'로 통일)
    # 실제 멀티유저 환경에서는 사용자 인증을 통해 user_name을 동적으로 할당해야...
    manager = SecurityAgentManager(session_id="grayhound_cli_session", user_name="user")
    collector = ThreatIntelligenceCollector()
    
    while True:
        print("\n[  🐺 메인 메뉴 🐺  ]")
        print("1. 🕵️  블로트웨어 DB 업데이트 (AI 기반 동적 쿼리 생성)")
        print("2. 🗄️  블로트웨어 DB 목록 보기")
        print("3. 💻  내 PC 스캔 및 정리")
        print("4. 🛡️  무시 목록 관리")
        print("5. 🐾  종료")
        choice = input("선택 > ").strip()
        
        if choice == '1':
            await update_db_workflow(collector)
            
        elif choice == '2':
            print("\n⏳ MongoDB에서 전체 블로트웨어 목록을 가져옵니다...")
            full_threat_list = await database.async_get_threats_with_ignore_status("user")

            if not full_threat_list:
                print("\n❌ DB에 저장된 블로트웨어 정보가 없습니다. 먼저 DB 업데이트를 실행해주세요.")
                continue

            print("\n--- 전체 블로트웨어 DB 목록 ---")
            df = pd.DataFrame(full_threat_list)

            # 표 헤더를 한글로 변경하고, 보여줄 열을 선택
            df.rename(columns={
                'program_name': '프로그램명', 'risk_score': '위험도',
                'reason': '판단 이유', 'ignored': '무시 여부'
            }, inplace=True)
            print(df[['프로그램명', '위험도', '판단 이유', '무시 여부']].to_markdown(index=False))
            print("-" * 50)

        elif choice == '3':
            # 3.1 스캔
            print("\n🔍 시스템 스캔을 시작합니다...")
            result = await manager.scan_system()
            threats = result.get("threats")

            if not threats:
                print("\n🎉 축하합니다! 분석 결과, 제거할 블로트웨어가 발견되지 않았습니다. 쾌적한 상태입니다!")
                continue

            print("\n--- 스캔 결과: 다음 블로트웨어가 발견되었습니다 ---")
            df = pd.DataFrame(threats)
            print(df[['name', 'risk_score', 'reason']].to_markdown(index=False))
            print("-" * 50)

            # 3.2 정리
            cleanup_input = input("정리할 항목의 이름을 쉼표(,)로 구분해 입력하세요.\n('전체' 입력 시 모두 정리, 그냥 Enter 시 건너뛰기)\n> ").strip()

            if not cleanup_input:
                print("⏩ 작업을 건너뛰고 메뉴로 돌아갑니다.")
                continue

            cleanup_list = []
            if cleanup_input.lower() == '전체':
                cleanup_list = threats
            else:
                names_to_clean = [name.strip().lower() for name in cleanup_input.split(',')]
                cleanup_list = [t for t in threats if t['name'].lower() in names_to_clean]

            if not cleanup_list:
                print("❌ 정리할 항목이 없거나 잘못 입력했습니다. 메뉴로 돌아갑니다. 🐾")
                continue

            # 언어 선택
            lang_choice = input("리포트 언어를 선택하세요 (1: 한국어, 2: English) [1]: ").strip()
            language = 'en' if lang_choice == '2' else 'ko'

            print(f"\n🚀 {len(cleanup_list)}개 항목에 대한 정리 작업을 시작합니다.")
            cleanup_result = await manager.execute_cleanup(cleanup_list, language=language)

            print("\n--- AI 생성 리포트 ---")
            print(cleanup_result.get("llm_feedback", "리포트 생성에 실패했습니다."))
            print("-" * 23)

        elif choice == '4':
            await manage_ignore_list("user")
            
        elif choice == '5':
            print("\n🐾 Grayhound를 종료합니다. 다음에 또 만나요! 🐾")
            break
            
        else:
            print("❌ 잘못된 선택입니다. 다시 선택해주세요. 🐾")
            
async def manage_ignore_list(user_name: str):
    """무시 목록 관리 CLI (UX 개선 버전)"""
    while True:
        print("\n[  🛡️ 무시 목록 관리  ]")
        
        # 1. 전체 위협 목록과 현재 사용자의 무시 목록 상태를 함께 가져옵니다.
        full_threat_list = await database.async_get_threats_with_ignore_status(user_name)

        if not full_threat_list:
            print("\n❌ DB에 저장된 블로트웨어 정보가 없습니다. 먼저 DB 업데이트를 실행해주세요.")
            break

        # 2. Pandas DataFrame을 사용하여 표 형태로 목록을 보여줍니다.
        print("아래 표를 참고하여 무시 목록에 추가하거나 삭제할 프로그램의 이름을 입력하세요.")
        df = pd.DataFrame(full_threat_list)
        df.rename(columns={
            'program_name': '프로그램명', 'risk_score': '위험도',
            'reason': '판단 이유', 'ignored': '무시 여부'
        }, inplace=True)
        print(df[['프로그램명', '위험도', '판단 이유', '무시 여부']].to_markdown(index=False))
        print("-" * 50)

        # 3. 사용자에게 어떤 작업을 할지 선택지를 제공합니다.
        print("\n1. 무시 목록에 추가 | 2. 무시 목록에서 삭제 | 3. 메인 메뉴로 돌아가기")
        sub_choice = input("> ").strip()

        if sub_choice == '1':
            item_to_add = input("무시 목록에 추가할 프로그램의 정확한 이름을 입력하세요: ").strip()
            if item_to_add:
                await database.async_add_to_ignore_list(user_name, item_to_add)
                print(f"✅ '{item_to_add}'을(를) 무시 목록에 추가했습니다. 목록을 갱신합니다.")
                await asyncio.sleep(1) # 사용자에게 메시지를 인지할 시간을 줍니다.
        elif sub_choice == '2':
            item_to_remove = input("무시 목록에서 삭제할 프로그램의 이름을 입력하세요: ").strip()
            if item_to_remove:
                await database.async_remove_from_ignore_list(user_name, item_to_remove)
                print(f"✅ '{item_to_remove}'을(를) 무시 목록에서 삭제했습니다. 목록을 갱신합니다.")
                await asyncio.sleep(1)
        elif sub_choice == '3':
            print("⏩ 메인 메뉴로 돌아갑니다.")
            break
        else:
            print("❌ 잘못된 입력입니다.")
            await asyncio.sleep(1)
            
if __name__ == "__main__":
    # 로컬 에이전트(Optimizer.py)가 실행 중이어야 함.
    try:
        asyncio.run(main_cli())
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")