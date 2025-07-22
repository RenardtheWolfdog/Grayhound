# 보안 에이전트의 전체 워크플로를 지휘하는 핵심 관리자 모듈
# SecurityAgentManager.py

import asyncio
import logging
import re
from typing import List, Dict, Any, Optional

# 다른 모듈에서 필요한 클래스 및 함수 임포트
import database
from agent_client import OptimizerAgentClient
from google_ai_client import generate_text
from utils import mask_name, mask_name_for_guide, enhanced_mask_name

# ✅ 로깅 설정: 모든 레벨의 로그가 출력
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 기존 핸들러가 있으면 제거
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# 새로운 핸들러 추가
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class SecurityAgentManager:
    """Grayhound의 전체 워크플로를 관리하고 오케스트레이션하는 클래스 (Enhanced with Brand Matching)"""
    
    def __init__(self, session_id: str, user_name: str):
        self.session_id = session_id
        self.user_name = user_name
        self.optimizer_client = OptimizerAgentClient()
        logging.info(f"[SecurityAgentManager] Initialized for user '{user_name}' with session_id: {session_id}")
    
    def _normalize_program_name(self, name: str) -> str:
        """프로그램명을 정규화하여 매칭 정확도 향상"""
        if not name:
            return ""
              
        # 소문자 변환
        normalized = name.lower()
        
        # 버전 정보 제거 (v1.0, 2024, etc.)
        normalized = re.sub(r'\s*v?\d+\.\d+.*$', '', normalized)
        normalized = re.sub(r'\s*\d{4}.*$', '', normalized)
        
        # 아키텍처 정보 제거
        normalized = re.sub(r'\s*\(?(x86|x64|32bit|64bit|32비트|64비트)\)?', '', normalized)
        
        # 불필요한 문구 제거
        normalized = re.sub(r'\s*(internet\s+security|antivirus|security|suite|professional|pro|lite|free|trial)', '', normalized)
        
        # 특수 문자 및 괄호 내용 제거
        normalized = re.sub(r'\([^)]*\)', '', normalized)
        normalized = re.sub(r'[^\w\s가-힣]', ' ', normalized)
        
        # 중복 공백 제거
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
            
    def _extract_brand_keywords_from_name(self, name: str) -> List[str]:
        """프로그램명에서 브랜드 키워드 추출"""
        if not name:
            return []
        
        # 정규화된 이름에서 키워드 추출
        normalized = self._normalize_program_name(name)
        words = normalized.split()
        
        # 불용어 제거
        stopwords = {'the', 'and', 'for', 'with', 'software', 'program', 'application', 'app', 'tool', 'suite', 'service', 'system', 'windows', 'microsoft'}
        keywords = [word for word in words if len(word) >= 3 and word not in stopwords]
        
        return keywords

    def _is_protected_program(self, program_name: str, publisher: str = "") -> bool:
        """필수/보호 프로그램인지 확인"""
        program_lower = program_name.lower()
        publisher_lower = publisher.lower() if publisher else ""
        
        # 보호된 게시자 목록 (확장)
        protected_publishers = {
            "microsoft corporation", "microsoft", "nvidia corporation", "nvidia", 
            "intel corporation", "intel", "amd", "advanced micro devices, inc.", 
            "google llc", "google inc.", "apple inc.", "apple",
            "realtek semiconductor corp.", "realtek"
        }
        
        # 보호된 프로그램 패턴
        protected_patterns = [
            r'microsoft visual c\+\+',
            r'nvidia geforce',
            r'nvidia control panel',
            r'intel\s+(graphics|hd|uhd)',
            r'amd radeon',
            r'windows\s+(defender|security)',
            r'directx',
            r'\.net framework',
            r'visual studio',
            r'runtime',
            r'redistributable'
        ]
        
        # 게시자로 보호 여부 확인
        if publisher_lower and any(pub in publisher_lower for pub in protected_publishers):
            return True
        
        # 프로그램명 패턴으로 보호 여부 확인
        for pattern in protected_patterns:
            if re.search(pattern, program_lower):
                return True
        
        return False

    def _enhanced_threat_matching(self, program_name: str, threat_data: Dict[str, Any]) -> tuple[bool, str]:
        """Enhanced 위협 매칭 로직 - 브랜드 키워드 기반 매칭 포함"""
            
        # 먼저 보호 프로그램인지 확인
        publisher = threat_data.get('publisher', '')
        if self._is_protected_program(program_name, publisher):
            return False, "protected program - excluded from detection"
        
        program_lower = program_name.lower()
        program_normalized = self._normalize_program_name(program_name)
        
        # 기본 정보 추출
        db_program = threat_data.get('program_name', '').lower()
        generic_name = threat_data.get('generic_name', '').lower()
        publisher = threat_data.get('publisher', '').lower()
        brand_keywords = threat_data.get('brand_keywords', [])
        alternative_names = threat_data.get('alternative_names', [])
        process_names_str = threat_data.get('process_names', '')
        
        # 로깅을 위한 정보
        threat_info = f"DB: '{db_program}', Generic: '{generic_name}', Publisher: '{publisher}'"
        
        # 1. 정확한 일치
        if program_lower == db_program or program_lower == generic_name:
            return True, f"exact match with {threat_info}"
        
        # 2. 부분 문자열 포함
        if generic_name and len(generic_name) >= 3:
            if generic_name in program_lower or program_lower in generic_name:
                return True, f"substring match with generic_name '{generic_name}'"
        
        # 3. 정규화된 이름 기반 매칭
        db_normalized = self._normalize_program_name(threat_data.get('program_name', ''))
        if program_normalized and db_normalized and len(program_normalized) >= 4:
            if program_normalized == db_normalized:
                return True, f"normalized exact match: '{program_normalized}'"
        
        # 4. 브랜드 키워드 기반 매칭
        if brand_keywords and len(brand_keywords) > 0:
            for brand_keyword in brand_keywords:
                if isinstance(brand_keyword, str) and len(brand_keyword) >= 4:
                    brand_lower = brand_keyword.lower()
                    
                    # 보호된 브랜드는 절대 매칭하지 않음
                    protected_brands = {'microsoft', 'nvidia', 'intel', 'amd', 'google', 'apple', 'adobe'}
                    if brand_lower in protected_brands:
                        continue
                    
                    # 단어 경계를 사용한 정확한 매칭만 허용
                    pattern = r'\b' + re.escape(brand_lower) + r'\b'
                    if re.search(pattern, program_lower):
                        return True, f"brand keyword exact word match: '{brand_keyword}'"
        
        # 5. 대체명 기반 매칭
        if alternative_names:
            for alt_name in alternative_names:
                if isinstance(alt_name, str) and len(alt_name) >= 3:
                    alt_lower = alt_name.lower()
                    alt_normalized = self._normalize_program_name(alt_name)
                        
                    # 정확한 매칭만 허용
                    if (program_lower == alt_lower or 
                        (alt_normalized and program_normalized == alt_normalized)):
                        return True, f"alternative name exact match: '{alt_name}'"
        
        # 6. 프로세스명 기반 매칭
        if process_names_str:
            # 쉼표, 세미콜론, 파이프로 구분된 프로세스 이름들을 파싱
            separators = [',', ';', '|']
            process_names = [process_names_str]
            
            for sep in separators:
                new_list = []
                for item in process_names:
                    new_list.extend(item.split(sep))
                process_names = new_list
            
            db_process_list = [p.strip().lower() for p in process_names if p.strip()]
            
            # 프로그램 이름이 프로세스 목록에 있는지 확인
            if program_lower in db_process_list:
                return True, f"process name exact match"
            
            # 부분 매칭 (3글자 이상)
            for proc in db_process_list:
                if len(proc) > 3 and (proc in program_lower or program_lower in proc):
                    return True, f"process name partial match: '{proc}'"
                
        return False, "no match found"

    def _analyze_threats(self, profile: Dict, threat_db: List[Dict], ignore_list: List[str], risk_threshold: int) -> List[Dict]:
        """
        Enhanced 시스템 프로파일과 위협 DB 비교
        """
        # 1. 빠른 조회를 위해 사용자 무시 목록을 Set으로 변환
        ignore_set = {item.lower() for item in ignore_list}
        
        # 2. 탐지된 위협의 중복 추가를 방지하기 위한 Set 생성
        already_identified_names = set()
        
        identified_threats = []
        
        # 3. 설치된 프로그램 목록과 실행 중인 프로세스 목록
        installed_programs = profile.get("installed_programs", [])
        running_processes = profile.get("running_processes", [])
        
        logging.info(f"[DEBUG] installed_programs: {len(installed_programs)}")
        logging.info(f"[DEBUG] running_processes: {len(running_processes)}")
        logging.info(f"[DEBUG] threat_db: {len(threat_db)}")
        logging.info(f"[DEBUG] Enhanced matching enabled with brand keywords support")

        # 모든 검사 대상을 합침
        all_programs_to_check = installed_programs + running_processes

        # 4. Enhanced 검사 대상 목록을 순회하며 위협 DB와 비교
        checked_count = 0
        protected_count = 0
        
        for program in all_programs_to_check:
            checked_count += 1
            program_name = program.get('name', 'N/A')
            program_name_lower = program_name.lower()
            publisher = program.get('publisher', '')

            # 20개마다 진행상황 로깅
            if checked_count % 20 == 0:
                logger.info(f"[PROGRESS] {checked_count}/{len(all_programs_to_check)} 프로그램 검사 완료...")

            if program_name_lower in already_identified_names or program_name_lower in ignore_set:
                continue

            # 보호 프로그램 사전 체크
            if self._is_protected_program(program_name, publisher):
                protected_count += 1
                logging.debug(f"[PROTECTED] Skipping protected program: '{program_name}' (Publisher: {publisher})")
                continue

            # 5. Enhanced 위협 DB의 각 항목과 비교
            for threat in threat_db:
                logging.debug(f"[DEBUG] Comparing '{program_name}' with threat: {threat.get('program_name', 'Unknown')}")
                
                # Enhanced 매칭 로직 사용
                is_detected, detection_reason = self._enhanced_threat_matching(program_name, threat)
                
                # 탐지된 경우 위협 정보 추가
                if is_detected:
                    current_risk = threat.get('risk_score', 0)
                    logging.debug(f"[DEBUG] ✅ Successfully detected '{program_name}'! Risk: {current_risk}, Reason: {detection_reason}")
                    
                    if current_risk >= risk_threshold:
                        base_reason = threat.get('reason', 'Included in known bloatware/grayware list.')
                        
                        # 변종 처리 로직
                        reason_for_display = base_reason
                        db_program_name = threat.get('program_name', '')
                        if program_name_lower != db_program_name.lower():
                            reason_for_display = f"Detected as a variant of '{mask_name(db_program_name)}' ({base_reason})"
                        
                        threat_details = {
                            "name": program_name,
                            "masked_name": enhanced_mask_name(program_name, threat.get('generic_name', '')),
                            "reason": reason_for_display,
                            "risk_score": current_risk,
                            "path": program.get('install_location') or program.get('path', 'N/A'),
                            "pid": program.get('pid', None),
                            "detection_method": detection_reason  # 디버깅용: 탐지 방법 추가
                        }
                        identified_threats.append(threat_details)
                        already_identified_names.add(program_name_lower)
                        
                        logging.info(f"[ENHANCED] Added to threats: '{program_name}' (Method: {detection_reason})")
                        # 하나의 프로그램은 하나의 위협으로만 매칭되면 되므로, 내부 루프를 탈출
                        break
                    else:
                        logging.debug(f"[DEBUG] {program_name} detected but risk_score < {risk_threshold}")
        
        # 6. 위험도가 높은 순으로 정렬하여 반환
        identified_threats.sort(key=lambda x: x['risk_score'], reverse=True)
        logger.info(f"[ENHANCED] Total identified threats: {len(identified_threats)}")
        logger.info(f"[ENHANCED] Total protected programs: {protected_count}")
        
        # 탐지 방법별 통계 로깅
        detection_methods = {}
        for threat in identified_threats:
            method = threat.get('detection_method', 'unknown')
            detection_methods[method] = detection_methods.get(method, 0) + 1
        
        logger.info(f"[ENHANCED] Detection methods used: {detection_methods}")
        
        return identified_threats
            
    async def scan_system(self, ignore_list: Optional[List[str]] = None, risk_threshold: int = 4) -> Dict[str, Any]:
        """시스템 스캔의 전체 과정을 조율하고 최종 분석 결과를 반환 (Enhanced)"""
        try:
            # 1. Local Agent에 연결하여 시스템 프로파일링 요청
            logging.info(f"[{self.session_id}] Starting enhanced system scan with Local Agent...")
            system_profile = await self.optimizer_client.get_system_profile()
            if not system_profile:
                return {"error": "Unable to communicate with Local Agent (Optimizer). Please check if the agent is running."}
            logging.info(f"[{self.session_id}] System profile collection completed.")
            
            # 2. MongoDB에서 Enhanced 위협 인텔리전스 및 사용자 무시 목록 비동기 조회
            threat_data_task = database.async_get_all_threats()
            db_ignore_list_task = database.async_get_ignore_list_for_user(self.user_name)
            threat_db, db_ignore_list = await asyncio.gather(threat_data_task, db_ignore_list_task)
            
            # DB의 영구 무시 목록과 전달받은 임시 무시 목록을 통합
            final_ignore_list = db_ignore_list
            if ignore_list:
                final_ignore_list.extend(ignore_list)

            # 4. Enhanced 위협 분석: 브랜드 키워드 기반 매칭 포함
            logging.info(f"[{self.session_id}] Enhanced threat analysis started (Risk Threshold: {risk_threshold}, Brand Matching: Enabled)...")
            found_threats = self._analyze_threats(system_profile, threat_db, final_ignore_list, risk_threshold)
            logging.info(f"[{self.session_id}] Enhanced threat analysis completed. Found {len(found_threats)} potential threats.")
           
            return {"threats": found_threats}
        
        except Exception as e:
            logging.error(f"[{self.session_id}] Error during enhanced system scan: {e}", exc_info=True)
            return {"error": f"Unexpected error occurred during enhanced system scan: {e}"}
    
    async def execute_cleanup(self, cleanup_list: List[Dict], language: str = 'en') -> Dict[str, Any]:
        """Local Agent에 최종 정리 목록을 전달하고, 실행 전후 성능 및 LLM 피드백을 포함한 최종 결과를 반환"""
        try:
            # Grayhound가 이해할 수 있는 형식으로 데이터 변환
            name_to_masked_name = {item["name"]: item.get("masked_name", mask_name(item["name"])) for item in cleanup_list}

            optimizer_cleanup_list = [{"name": item["name"], "command_type": "uninstall_program", "program_name": item["name"]} for item in cleanup_list]
  
            logging.info(f"[{self.session_id}] Local Agent에 {len(optimizer_cleanup_list)}개의 항목 정리 요청...")
            agent_results = await self.optimizer_client.execute_cleanup_plan(optimizer_cleanup_list)
            
            if agent_results is None:
                return {"error": "Failed to execute cleanup. Unable to communicate with Local Agent."}

            comprehensive_results = []
            for res in agent_results:
                original_name = res.get("name")
                res["masked_name"] = name_to_masked_name.get(original_name, mask_name(original_name))
                # 가이드를 위한 별도의 마스킹 이름 추가
                res["guide_masked_name"] = mask_name_for_guide(original_name)
                comprehensive_results.append(res)
                
            # LLM 피드백 생성 (언어 설정 전달)
            llm_feedback = await self._generate_llm_feedback(comprehensive_results, language)

            return {"results": comprehensive_results, "llm_feedback": llm_feedback}

        except Exception as e:
            logging.error(f"[{self.session_id}] Error during threat removal: {e}", exc_info=True)
            return {"error": f"Unexpected error occurred during threat removal: {e}"}
        
    async def _generate_llm_feedback(self, cleanup_results: List, language: str = "en") -> str:
        """분석 결과를 바탕으로 사용자에게 제공할 LLM 피드백 생성"""
        logging.info(f"LLM feedback generation started... (language: {language}) 🌒")

        if not cleanup_results:
            return "정리된 항목이 없습니다." if language == 'ko' else "No items were cleaned."
        
       # 구조화된 결과에서 성공/실패 분리
        successful_items = [res.get('masked_name', res.get('name')) for res in cleanup_results if res.get('status') == 'success']
        failed_items = [res.get('masked_name', res.get('name')) for res in cleanup_results if res.get('status') == 'failure']
           
        # 언어에 따른 프롬프트 생성
        prompts = {
            'ko': f"""
            PC 최적화 작업 'Grayhound'가 방금 완료되었습니다.
            - 성공적으로 제거한 블로트웨어 프로그램: {', '.join(successful_items) if successful_items else '없음'}
            - 제거에 실패한 블로트웨어 프로그램: {', '.join(failed_items) if failed_items else '없음'}

            이 결과를 바탕으로, 사용자에게 작업 완료를 알리는 친절하고 명확한 리포트를 작성해주세요.
            성공과 실패 여부를 명확히 구분해서 알려주고, 전반적으로 PC가 더 쾌적해졌을 것이라는 긍정적인 메시지를 전달해주세요.
            캐릭터 없이, 전문적이고 간결한 톤으로 작성해주세요.
            
            **중요: 반드시 한국어로 리포트를 작성해주세요. 작업 날짜와 시간은 기입하지 마세요.**
            """,
            'en': f"""
            The PC optimization task 'Grayhound' has just completed.
            - Successfully removed bloatware programs: {', '.join(successful_items) if successful_items else 'None'}
            - Failed to remove bloatware programs: {', '.join(failed_items) if failed_items else 'None'}

            Based on this, write a friendly and clear report for the user informing them of the completion.
            Clearly distinguish between success and failure, and convey a positive message that their PC should now be cleaner and faster.
            Write in a professional and concise tone, without any specific character persona.

            **IMPORTANT: Please write the report in English. Do not include the date and time of the task.**
            """,
            'ja': f"""
            PC 最適化タスク 'Grayhound' が完了しました。
            - 正常に削除されたブロットウェア プログラム: {', '.join(successful_items) if successful_items else 'なし'}
            - 削除に失敗したブロットウェア プログラム: {', '.join(failed_items) if failed_items else 'なし'}
            
            この結果をもとに、ユーザーに対して完了を通知する親切で明確なレポートを作成してください。
            成功と失敗を明確に区別し、PCがよりクリーンで高速になったことを伝える肯定的なメッセージを伝えてください。
            専門的で簡潔なトーンで、特定のキャラクターのパーソナリティを持たないように書いてください。
            
            **重要: 必ず日本語でレポートを作成してください。 タスクの日付と時刻は含めないでください。**
            """,
            'zh': f"""
            PC 优化任务 'Grayhound' 刚刚完成。
            - 成功删除的程序: {', '.join(successful_items) if successful_items else '无'}
            - 删除失败的程序: {', '.join(failed_items) if failed_items else '无'}
            
            在此基礎上，為使用者撰寫一份友好清晰的報告，告知他們操作已完成。
            報告應清楚區分成功和失敗，並傳達正面的訊息，告知使用者電腦現在應該更乾淨、更快速。
            報告應使用專業簡潔的語氣，避免任何特定的人物角色。
            
            **重要：请务必用中文撰写报告。 请勿包含任务的日期和时间。**
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