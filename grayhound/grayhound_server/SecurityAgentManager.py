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
        if generic_name and len(generic_name) >= 5:
            # 단순 포함이 아닌, 의미있는 부분 매칭인지 확인
            if generic_name in program_lower:
                # generic_name이 프로그램명의 상당 부분을 차지하는지 확인
                if len(generic_name) / len(program_lower) >= 0.5:  # 50% 이상 차지
                    return True, f"significant substring match with generic_name '{generic_name}'"
            
        # 3. 정규화된 이름 기반 매칭
        db_normalized = self._normalize_program_name(threat_data.get('program_name', ''))
        if program_normalized and db_normalized and program_normalized == db_normalized:
            return True, f"normalized exact match: '{program_normalized}'"
        
    # 4. 브랜드 키워드 기반 매칭 (조건 강화)
        if brand_keywords and len(brand_keywords) > 0:
            matched_keywords = 0  # 변수 초기화
            total_valid_keywords = 0  # 유효한 키워드 수 추적
            
            for brand_keyword in brand_keywords:
                if isinstance(brand_keyword, str) and len(brand_keyword) >= 4:
                    brand_lower = brand_keyword.lower()
                    total_valid_keywords += 1
                    
                    # 보호된 브랜드는 절대 매칭하지 않음
                    protected_brands = {'microsoft', 'nvidia', 'intel', 'amd', 'google', 'apple', 'adobe', 'windows'}
                    if brand_lower in protected_brands:
                        continue
                    
                    # 단어 경계를 사용한 정확한 매칭
                    pattern = r'\b' + re.escape(brand_lower) + r'\b'
                    if re.search(pattern, program_lower):
                        matched_keywords += 1
            
            # 브랜드 키워드는 2개 이상 매칭되어야 함 (단일 키워드 매칭은 부정확할 수 있음)
            # 유효한 키워드가 있고 매칭된 경우에만 처리
            if matched_keywords > 0:
                if matched_keywords >= 2 or (matched_keywords == 1 and total_valid_keywords == 1):
                    return True, f"brand keyword match: {matched_keywords} keywords matched"
            
        # 5. 대체명 기반 매칭
        if alternative_names:
            for alt_name in alternative_names:
                if isinstance(alt_name, str) and len(alt_name) >= 5:
                    alt_lower = alt_name.lower()
                    alt_normalized = self._normalize_program_name(alt_name)
                        
                    # 정확한 매칭만 허용 또는 정규화된 매칭만 허용
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
            
            # 프로세스명 부분 매칭은 더 엄격하게 (최소 5글자 이상)
            for proc in db_process_list:
                if len(proc) >= 5:
                    # 프로세스명이 프로그램명의 핵심 부분인지 확인
                    if proc in program_lower and len(proc) / len(program_lower) >= 0.4:  # 40% 이상
                        return True, f"process name core match: '{proc}'"
        
        # 7. 추가 안전장치: 게시자명 확인 (동일 게시자의 제품인 경우)
        if publisher and len(publisher) >= 4:
            # 게시자명이 프로그램명에 포함되어 있고, DB의 게시자와 일치하는 경우
            publisher_pattern = r'\b' + re.escape(publisher) + r'\b'
            if re.search(publisher_pattern, program_lower, re.IGNORECASE):
                # 하지만 이것만으로는 부족하므로, 추가 조건 확인
                if generic_name and len(generic_name) >= 4 and generic_name in program_lower:
                    return True, f"publisher + generic name match: '{publisher}'"
                    
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
                logging.debug(f"[PROTECTED] Skipping protected program: '{mask_name(program_name)}' (Publisher: {mask_name(publisher)})")
                continue

            # 5. Enhanced 위협 DB의 각 항목과 비교
            for threat in threat_db:
                logging.debug(f"[DEBUG] Comparing '{mask_name(program_name)}' with threat: {mask_name(threat.get('program_name', 'Unknown'))}")
                
                # Enhanced 매칭 로직 사용
                is_detected, detection_reason = self._enhanced_threat_matching(program_name, threat)
                
                # 탐지된 경우 위협 정보 추가
                if is_detected:
                    current_risk = threat.get('risk_score', 0)
                    logging.debug(f"[DEBUG] ✅ Successfully detected '{mask_name(program_name)}'! Risk: {current_risk}, Reason: {detection_reason}")
                    
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
                            "detection_method": detection_reason,
                            # 🔥 탐지 컨텍스트 추가
                            "detection_context": {
                                "matched_threat": threat,  # 매칭된 DB threat 전체 정보
                                "program_type": "installed_program" if program in installed_programs else "running_process",
                                "matched_fields": {  # 어떤 필드로 매칭되었는지
                                    "program_name": program_name,
                                    "db_program_name": threat.get('program_name', ''),
                                    "generic_name": threat.get('generic_name', ''),
                                    "process_names": threat.get('process_names', ''),
                                    "brand_keywords": threat.get('brand_keywords', []),
                                    "alternative_names": threat.get('alternative_names', [])
                                }
                            }
                        }
                        identified_threats.append(threat_details)
                        already_identified_names.add(program_name_lower)
                        
                        logging.info(f"[ENHANCED] Added to threats: '{mask_name(program_name)}' (Method: {detection_reason})")
                        # 하나의 프로그램은 하나의 위협으로만 매칭되면 되므로, 내부 루프를 탈출
                        break
                    else:
                        logging.debug(f"[DEBUG] {mask_name(program_name)} detected but risk_score < {risk_threshold}")
        
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
    
    async def execute_phase_a_cleanup(self, cleanup_list: List[Dict], language: str = 'en') -> Dict[str, Any]:
        """Phase A: 1단계 기본 삭제만 수행"""
        try:
            # Grayhound Optimizer에 Phase A 전용 요청
            name_to_masked_name = {item["name"]: item.get("masked_name", mask_name(item["name"])) for item in cleanup_list}

            optimizer_cleanup_list = [{"name": item["name"], "command_type": "uninstall_program", "program_name": item["name"]} for item in cleanup_list]

            logging.info(f"[{self.session_id}] Phase A: Requesting basic cleanup of {len(optimizer_cleanup_list)} items...")
            agent_results = await self.optimizer_client.execute_cleanup_plan(optimizer_cleanup_list)
            
            if agent_results is None:
                return {"error": "Failed to execute Phase A cleanup. Unable to communicate with Local Agent."}

            # 결과 마스킹 처리
            comprehensive_results = []
            for res in agent_results:
                original_name = res.get("name")
                res["masked_name"] = name_to_masked_name.get(original_name, mask_name(original_name))
                res["guide_masked_name"] = mask_name_for_guide(original_name)
                comprehensive_results.append(res)

            # Phase A 전용 LLM 피드백 생성
            phase_a_feedback = await self._generate_phase_a_feedback(comprehensive_results, language)

            return {"results": comprehensive_results, "llm_feedback": phase_a_feedback}

        except Exception as e:
            logging.error(f"[{self.session_id}] Error during Phase A cleanup: {e}", exc_info=True)
            return {"error": f"Unexpected error occurred during Phase A cleanup: {e}"}

    async def _generate_phase_a_feedback(self, cleanup_results: List, language: str = "en") -> str:
        """Phase A 결과에 대한 LLM 피드백 생성"""
        logging.info(f"Phase A feedback generation started... (language: {language}) 🌒")

        if not cleanup_results:
            return "Phase A cleanup completed with no items."
        
        # Phase A 결과 분석
        successful_items = [res.get('masked_name', res.get('name')) for res in cleanup_results if res.get('status') == 'success']
        failed_items = [res.get('masked_name', res.get('name')) for res in cleanup_results if res.get('status') in ['phase_a_failed', 'failure']]
        
        # 언어에 따른 프롬프트 생성
        prompts = {
            'ko': f"""
            PC 최적화 Phase A (기본 정리)가 완료되었습니다.
            - Phase A에서 성공적으로 제거된 프로그램: {', '.join(successful_items) if successful_items else '없음'}
            - Phase A에서 제거에 실패한 프로그램: {', '.join(failed_items) if failed_items else '없음'}

            이 결과를 바탕으로, 사용자에게 Phase A 완료를 알리는 간결하고 명확한 리포트를 작성해주세요.
            {f"실패한 항목들은 추가 단계(Phase B/C)에서 처리할 수 있다는 안내도 포함해주세요." if failed_items else ""}
            전문적이고 친절한 톤으로 작성해주세요.

            **중요: 반드시 한국어로 리포트를 작성해주세요.**
            """,
            'en': f"""
            PC optimization Phase A (basic cleanup) has completed.
            - Programs successfully removed in Phase A: {', '.join(successful_items) if successful_items else 'None'}
            - Programs that failed to be removed in Phase A: {', '.join(failed_items) if failed_items else 'None'}

            Based on this, write a concise and clear report informing the user of Phase A completion.
            {f"Also mention that failed items can be handled in additional steps (Phase B/C)." if failed_items else ""}
            Write in a professional and friendly tone.

            **IMPORTANT: Please write the report in English.**
            """,
            'ja': f"""
            PC最適化 Phase A（基本クリーンアップ）が完了しました。
            - Phase Aで正常に削除されたプログラム: {', '.join(successful_items) if successful_items else 'なし'}
            - Phase Aで削除に失敗したプログラム: {', '.join(failed_items) if failed_items else 'なし'}
            
            この結果をもとに、ユーザーに Phase A の完了を知らせる簡潔で明確なレポートを作成してください。
            {f"失敗した項目は追加ステップ（Phase B/C）で処理できることも含めてください。" if failed_items else ""}
            専門的で親切なトーンで書いてください。
            
            **重要: 必ず日本語でレポートを作成してください。**
            """,
            'zh': f"""
            PC 优化 Phase A（基本清理）已完成。
            - Phase A 中成功删除的程序: {', '.join(successful_items) if successful_items else '无'}
            - Phase A 中删除失败的程序: {', '.join(failed_items) if failed_items else '无'}
            
            基于此结果，撰写一份简洁明了的报告，告知用户 Phase A 的完成情况。
            {f"也请提及失败的项目可以在后续步骤（Phase B/C）中处理。" if failed_items else ""}
            以专业和友好的语气撰写。
            
            **重要：请务必用中文撰写报告。**
            """
        }
        
        prompt = prompts.get(language, prompts['en'])
        
        # Google AI 클라이언트 호출
        feedback = generate_text(prompt, temperature=0.5)
        
        if "An error occurred" in feedback:
            default_messages = {
                'ko': f"Phase A 완료! {len(successful_items)}개 프로그램이 제거되었습니다." + (f" {len(failed_items)}개 항목은 추가 단계가 필요합니다." if failed_items else ""),
                'en': f"Phase A complete! {len(successful_items)} programs removed." + (f" {len(failed_items)} items need additional steps." if failed_items else ""),
                'ja': f"Phase A 完了！{len(successful_items)}個のプログラムが削除されました。" + (f" {len(failed_items)}個の項目は追加ステップが必要です。" if failed_items else ""),
                'zh': f"Phase A 完成！{len(successful_items)}个程序被删除。" + (f" {len(failed_items)}个项目需要额外步骤。" if failed_items else "")
            }
            return default_messages.get(language, default_messages['en'])
            
        logging.info("Phase A LLM 피드백 생성 완료!")
        return feedback

    async def _generate_comprehensive_feedback(self, all_results: List, language: str = "en") -> str:
        """모든 Phase 결과를 종합한 포괄적 LLM 피드백 생성"""
        logging.info(f"Comprehensive feedback generation started... (language: {language}) 🌒")

        if not all_results:
            return "No items were processed."
        
        # 결과를 Phase별로 분류
        phase_a_success = []
        phase_b_success = []
        phase_c_success = []
        not_removed = [] # 제거 실패 항목
        total_failures = []
        
        for result in all_results:
            name = result.get('masked_name', result.get('name', 'Unknown'))
            status = result.get('status', 'unknown')
            phase = result.get('phase_completed', 'unknown')
            
            if status == 'success':
                if phase == 'phase_a':
                    phase_a_success.append(name)
                elif phase == 'phase_b' or phase == 'manual':
                    phase_b_success.append(name)
                elif phase == 'phase_c':
                    phase_c_success.append(name)
            elif phase == 'skipped' or status == 'still_exists':
                not_removed.append(name)
            else:
                total_failures.append(name)
        
        # 언어에 따른 포괄적 프롬프트 생성
        prompts = {
            'ko': f"""
            Grayhound PC 최적화 작업이 완료되었습니다.

            **단계별 제거 결과:**
            - Phase A (기본 제거)에서 성공: {', '.join(phase_a_success) if phase_a_success else '없음'}
            - Phase B (Windows 설정)에서 성공: {', '.join(phase_b_success) if phase_b_success else '없음'}
            - Phase C (강제 제거)에서 성공: {', '.join(phase_c_success) if phase_c_success else '없음'}
            - 제거되지 않음 (사용자 선택): {', '.join(not_removed) if not_removed else '없음'}
            - 모든 방법으로 제거 실패: {', '.join(total_failures) if total_failures else '없음'}

            이 결과를 바탕으로, 사용자에게 전체 최적화 작업의 완료를 알리는 포괄적이고 친절한 리포트를 작성해주세요.
            각 단계에서 어떤 프로그램이 어떻게 제거되었는지 명확히 설명하고, 
            제거되지 않은 항목은 사용자가 의도적으로 남겨둔 것일 수 있다는 점을 언급해주세요.
            전반적으로 PC가 얼마나 깨끗해졌는지 강조해주세요.

            **중요: 반드시 한국어로 리포트를 작성해주세요.**
            """,
            'en': f"""
            Grayhound PC optimization has been completed.

            **Step-by-step removal results:**
            - Succeeded in Phase A (basic removal): {', '.join(phase_a_success) if phase_a_success else 'None'}
            - Succeeded in Phase B (Windows Settings): {', '.join(phase_b_success) if phase_b_success else 'None'}
            - Succeeded in Phase C (force removal): {', '.join(phase_c_success) if phase_c_success else 'None'}
            - Not removed (user choice): {', '.join(not_removed) if not_removed else 'None'}
            - Failed with all methods: {', '.join(total_failures) if total_failures else 'None'}

            Based on this, write a comprehensive and friendly report informing the user of the completion of the entire optimization task.
            Clearly explain which programs were removed at each stage,
            and mention that items not removed may have been intentionally kept by the user.
            Emphasize how much cleaner the PC has become overall.

            **IMPORTANT: Please write the report in English.**
            """,
            'ja': f"""
            Grayhound PC最適化作業が完了しました。

            **段階別削除結果:**
            - Phase A（基本削除）で成功: {', '.join(phase_a_success) if phase_a_success else 'なし'}
            - Phase B（Windows設定）で成功: {', '.join(phase_b_success) if phase_b_success else 'なし'}
            - Phase C（強制削除）で成功: {', '.join(phase_c_success) if phase_c_success else 'なし'}
            - 削除されず（ユーザーの選択）: {', '.join(not_removed) if not_removed else 'なし'}
            - 全ての方法で失敗: {', '.join(total_failures) if total_failures else 'なし'}

            この結果をもとに、ユーザーに全体の最適化作業の完了を知らせる包括的で親切なレポートを作成してください。
            各段階でどのプログラムがどのように削除されたかを明確に説明し、
            削除されなかった項目はユーザーが意図的に残したものである可能性があることに言及してください。
            全体的にPCがどれだけクリーンになったかを強調してください。

            **重要: 必ず日本語でレポートを作成してください。**
            """,
            'zh': f"""
            PC 优化任务 'Grayhound' 刚刚完成。
            - Phase A 中成功删除的程序: {', '.join(phase_a_success) if phase_a_success else '无'}
            - Phase B 中成功删除的程序: {', '.join(phase_b_success) if phase_b_success else '无'}
            - Phase C 中成功删除的程序: {', '.join(phase_c_success) if phase_c_success else '无'}
            - 未删除 (用户选择): {', '.join(not_removed) if not_removed else '无'}
            - 所有阶段都失败: {', '.join(total_failures) if total_failures else '无'}

            基于此结果，撰写一份简洁明了的报告，告知用户整个优化任务的完成情况。
            明确说明每个阶段删除了哪些程序，并提及未删除的项目可能是用户有意保留的。
            强调整体上PC变得有多干净。
            如果存在未删除的项目，也请提供简单的手动删除方法。

            **重要：请务必用中文撰写报告。**
            """
        }
        
        prompt = prompts.get(language, prompts['en'])
        
        # Google AI 클라이언트 호출
        feedback = generate_text(prompt, temperature=0.5)
        
        if "An error occurred" in feedback:
            total_success = len(phase_a_success) + len(phase_b_success) + len(phase_c_success)
            default_messages = {
                'ko': f"최적화 완료! 총 {total_success}개 프로그램이 제거되었습니다. PC가 더욱 깨끗해졌습니다!",
                'en': f"Optimization complete! Total {total_success} programs removed. Your PC is now cleaner!",
                'ja': f"最適化完了！合計{total_success}個のプログラムが削除されました。PCがよりクリーンになりました！",
                'zh': f"优化完成！总共{total_success}个程序被删除。您的电脑现在应该更干净了！"
            }
            return default_messages.get(language, default_messages['en'])
            
        logging.info("포괄적 LLM 피드백 생성 완료!")
        return feedback
        
    async def _generate_llm_feedback(self, cleanup_results: List, language: str = "en") -> str:
        """분석 결과를 바탕으로 사용자에게 제공할 LLM (일반) 피드백 생성"""
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