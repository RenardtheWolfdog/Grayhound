# 보안 에이전트의 전체 워크플로를 지휘하는 핵심 관리자 모듈
# SecurityAgentManager.py

import asyncio
import logging
from typing import List, Dict, Any, Optional

# 다른 모듈에서 필요한 클래스 및 함수 임포트
import database
from agent_client import OptimizerAgentClient
from google_ai_client import generate_text
from utils import mask_name

class SecurityAgentManager:
    """Grayhound의 전체 워크플로를 관리하고 오케스트레이션하는 클래스"""
    
    def __init__(self, session_id: str, user_name: str):
        self.session_id = session_id
        self.user_name = user_name
        self.optimizer_client = OptimizerAgentClient()
        logging.info(f"[SecurityAgentManager] Initialized for user '{user_name}' with session_id: {session_id}")
            
    async def scan_system(self, ignore_list: Optional[List[str]] = None, risk_threshold: int = 4) -> Dict[str, Any]:
        """시스템 스캔의 전체 과정을 조율하고 최종 분석 결과를 반환"""
        try:
            # 1. Local Agent에 연결하여 시스템 프로파일링 요청
            logging.info(f"[{self.session_id}] Local Agent로부터 시스템 프로파일 수집 시작... Starting to collect system profile from Local Agent.")
            system_profile = await self.optimizer_client.get_system_profile()
            if not system_profile:
                return {"error": "로컬 시스템 에이전트(Optimizer)와 통신할 수 없습니다. 에이전트가 실행 중인지 확인해 주세요. Cannot communicate with the local system agent (Optimizer). Please ensure the agent is running."}
            logging.info(f"[{self.session_id}] 시스템 프로파일 수집 완료. System profile collection complete.")
            
            # 2. MongoDB에서 위협 인텔리전스 및 사용자 무시 목록 비동기 조회
            threat_data_task = database.async_get_all_threats()
            db_ignore_list_task = database.async_get_ignore_list_for_user(self.user_name) # 사용자 무시 목록 조회
            threat_db, db_ignore_list = await asyncio.gather(threat_data_task, db_ignore_list_task)
            
            # DB의 영구 무시 목록과 전달받은 임시 무시 목록을 통합합니다.
            final_ignore_list = db_ignore_list
            if ignore_list:
                final_ignore_list.extend(ignore_list)

            # 4. 위협 분석: 시스템 프로파일, 위협 DB, 무시 목록, 위험도 임계값으로 비교
            logging.info(f"[{self.session_id}] 위협 분석 시작 (Risk Threshold: {risk_threshold})...")
            found_threats = self._analyze_threats(system_profile, threat_db, final_ignore_list, risk_threshold)
            logging.info(f"[{self.session_id}] 위협 분석 완료. {len(found_threats)}개의 잠재적 위협 발견.")
           
            return {"threats": found_threats}
        
        except Exception as e:
            logging.error(f"[{self.session_id}] 시스템 스캔 중 오류 발생: {e}", exc_info=True)
            return {"error": f"시스템 스캔 중 예상치 못한 오류 발생: {e}"}
    
    def _analyze_threats(self, profile: Dict, threat_db: List[Dict], ignore_list: List[str], risk_threshold: int) -> List[Dict]:
        """
        시스템 프로파일(설치된 프로그램, 실행 중인 프로세스)과 위협 DB를 비교하여
        대표 명칭(generic_name) 기반으로 잠재적 위협 목록을 생성
        """
        # 1. 빠른 조회를 위해 사용자 무시 목록을 Set으로 변환
        ignore_set = {item.lower() for item in ignore_list}
        
        # 2. 탐지된 위협의 중복 추가를 방지하기 위한 Set 생성
        already_identified_names = set()
        
        identified_threats = []
        
        # 3. 설치된 프로그램 목록과 실행 중인 프로세스 목록을 합쳐서 검사 대상으로 삼음
        programs_to_check = profile.get("installed_programs", []) + profile.get("running_processes", [])

        # 4. 검사 대상 목록을 순회하며 위협 DB와 비교
        for program in programs_to_check:
            program_name = program.get('name', 'N/A')
            program_name_lower = program_name.lower()

            if program_name_lower in already_identified_names or program_name_lower in ignore_set:
                continue

            # 5. 위협 DB의 각 항목과 비교
            for threat in threat_db:
                db_program_name = threat.get('program_name', '')
                # 5-1. DB에 'generic_name'이 있으면 사용하고, 없으면 'program_name'을 대표 이름으로 사용
                generic_name = threat.get('generic_name', db_program_name).lower()
                if not generic_name:
                    continue

                # 5-2. 프로그램 이름이 대표 이름으로 시작하는지 확인하여 변종을 탐지
                if program_name_lower.startswith(generic_name):
                    current_risk = threat.get('risk_score', 0)
                    
                    if current_risk >= risk_threshold:
                        base_reason = threat.get('reason', 'Included in known bloatware/grayware list.')
                        masked_display_name = threat.get('masked_name', mask_name(db_program_name))
                        
                        # 실제 탐지된 이름과 DB의 이름이 다를 경우, 변종임을 명시
                        if program_name_lower != db_program_name.lower():
                            reason_for_display = f"Detected as a variant of '{mask_name(db_program_name)}' ({base_reason})"
                        else:
                            reason_for_display = base_reason
                        threat_details = {
                            "name": program_name, # 실제 PC에서 발견된 프로그램 이름
                            "masked_name": mask_name(program_name), # 스캔 결과에도 마스킹된 이름을 추가
                            "reason": reason_for_display, # 위협 사유 (변종 여부 포함)
                            "risk_score": current_risk, # DB 기반 위험도
                            "path": program.get('install_location') or program.get('path', 'N/A'),
                            "pid": program.get('pid', None) # 프로세스인 경우 PID 정보 추가
                        }
                        identified_threats.append(threat_details)
                        already_identified_names.add(program_name_lower)
                        
                        # 하나의 프로그램은 하나의 위협으로만 매칭되면 되므로, 내부 루프를 탈출
                        break
        
        # 6. 위험도가 높은 순으로 정렬하여 반환
        identified_threats.sort(key=lambda x: x['risk_score'], reverse=True)
        return identified_threats
    
    async def execute_cleanup(self, cleanup_list: List[Dict], language: str = 'en') -> Dict[str, Any]:
        """Local Agent에 최종 정리 목록을 전달하고, 실행 전후 성능 및 LLM 피드백을 포함한 최종 결과를 반환"""
        try:
            # Grayhound가 이해할 수 있는 형식으로 데이터 변환
            name_to_masked_name = {item["name"]: item.get("masked_name", mask_name(item["name"])) for item in cleanup_list}

            optimizer_cleanup_list = [{"name": item["name"], "command_type": "uninstall_program", "program_name": item["name"]} for item in cleanup_list]
  
            logging.info(f"[{self.session_id}] Local Agent에 {len(optimizer_cleanup_list)}개의 항목 정리 요청... Requesting cleanup of {len(optimizer_cleanup_list)} items from Local Agent.")
            agent_results = await self.optimizer_client.execute_cleanup_plan(optimizer_cleanup_list)
            
            if agent_results is None:
                return {"error": "정리 작업 실행에 실패했습니다. Local Agent와 통신할 수 없습니다."}

            comprehensive_results = []
            for res in agent_results:
                original_name = res.get("name")
                res["masked_name"] = name_to_masked_name.get(original_name, mask_name(original_name))
                comprehensive_results.append(res)

            # LLM 피드백 생성 (언어 설정 전달)
            llm_feedback = await self._generate_llm_feedback(comprehensive_results, language)

            return {"results": comprehensive_results, "llm_feedback": llm_feedback}

        except Exception as e:
            logging.error(f"[{self.session_id}] 위협 제거 중 오류 발생: {e}", exc_info=True)
            return {"error": f"위협 제거 중 예상치 못한 오류 발생: {e}"}
        
    async def _generate_llm_feedback(self, cleanup_results: List, language: str = "en") -> str:
        """분석 결과를 바탕으로 사용자에게 제공할 LLM 피드백 생성"""
        logging.info(f"LLM 피드백 생성 시작... (language: {language}) 🌒")

        if not cleanup_results:
            return "정리된 항목이 없습니다." if language == 'ko' else "No items were cleaned."
        
       # 구조화된 결과에서 성공/실패 분리
        successful_items = [res.get('masked_name', res.get('name')) for res in cleanup_results if res.get('status') == 'success']
        failed_items = [res.get('masked_name', res.get('name')) for res in cleanup_results if res.get('status') == 'failure']
           
        # 언어에 따른 프롬프트 생성
        prompts = {
            'ko': f"""
            PC 최적화 작업 'Grayhound'가 방금 완료되었습니다.
            - 성공적으로 제거한 프로그램: {', '.join(successful_items) if successful_items else '없음'}
            - 제거에 실패한 프로그램: {', '.join(failed_items) if failed_items else '없음'}

            이 결과를 바탕으로, 사용자에게 작업 완료를 알리는 친절하고 명확한 리포트를 작성해주세요.
            성공과 실패 여부를 명확히 구분해서 알려주고, 전반적으로 PC가 더 쾌적해졌을 것이라는 긍정적인 메시지를 전달해주세요.
            캐릭터 없이, 전문적이고 간결한 톤으로 작성해주세요.
            
            **중요: 반드시 한국어로 리포트를 작성해주세요.**
            """,
            'en': f"""
            The PC optimization task 'Grayhound' has just completed.
            - Successfully removed programs: {', '.join(successful_items) if successful_items else 'None'}
            - Failed to remove programs: {', '.join(failed_items) if failed_items else 'None'}

            Based on this, write a friendly and clear report for the user informing them of the completion.
            Clearly distinguish between success and failure, and convey a positive message that their PC should now be cleaner and faster.
            Write in a professional and concise tone, without any specific character persona.

            **IMPORTANT: Please write the report in English.**
            """,
            'ja': f"""
            PC 最適化タスク 'Grayhound' が完了しました。
            - 正常に削除されたプログラム: {', '.join(successful_items) if successful_items else 'なし'}
            - 削除に失敗したプログラム: {', '.join(failed_items) if failed_items else 'なし'}
            
            この結果をもとに、ユーザーに対して完了を通知する親切で明確なレポートを作成してください。
            成功と失敗を明確に区別し、PCがよりクリーンで高速になったことを伝える肯定的なメッセージを伝えてください。
            専門的で簡潔なトーンで、特定のキャラクターのパーソナリティを持たないように書いてください。
            
            **重要: 必ず日本語でレポートを作成してください。**
            """,
            'zh': f"""
            PC 优化任务 'Grayhound' 刚刚完成。
            - 成功删除的程序: {', '.join(successful_items) if successful_items else '无'}
            - 删除失败的程序: {', '.join(failed_items) if failed_items else '无'}
            
            在此基礎上，為使用者撰寫一份友好清晰的報告，告知他們操作已完成。
            報告應清楚區分成功和失敗，並傳達正面的訊息，告知使用者電腦現在應該更乾淨、更快速。
            報告應使用專業簡潔的語氣，避免任何特定的人物角色。
            
            **重要：请务必用中文撰写报告。**
            """
        }
        
        prompt = prompts.get(language, prompts['en']) # 기본값은 영어
        
        # Google AI 클라이언트 호출
        feedback = generate_text(prompt, temperature=0.5)
        
        if "An error occurred" in feedback:
            # 기본 대체 메시지도 언어에 맞게 수정
            default_messages = {
                'ko': "최적화를 완료했습니다! 이제 PC를 더 쾌적하게 사용할 수 있습니다.",
                'en': "Optimization complete! Your PC should now be cleaner and faster.",
                'ja': "最適化が完了しました！これで、PCがより快適に使用できるようになります。",
                'zh': "优化完成！您的电脑现在应该更干净、更快了。"
            }
            return default_messages.get(language, default_messages['en'])
            
        logging.info("LLM 피드백 생성 완료!")
        return feedback