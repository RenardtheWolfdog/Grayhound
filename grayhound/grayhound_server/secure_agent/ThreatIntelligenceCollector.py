# secure_agent/ThreatIntelligenceCollector.py
# Grayhound's Automated Threat Intelligence Collector Module

import json
import logging
import time
import re
import asyncio
import copy # 딕셔너리 복사를 위해 임포트
from typing import List, Dict, Any, Callable, Optional

# 프로젝트에 필요한 모듈 임포트
from google_ai_client import generate_text
from GoogleSearch_Grayhound import search_and_extract_text
import database # 중앙 DB 관리 모듈 임포트
from utils import mask_name

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(module)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class ThreatIntelligenceCollector:
    """외부 정보원으로부터 위협 인텔리전스를 수집, 분석하고 DB에 저장"""

    async def generate_dynamic_queries(self, country: str, os_type: str) -> Dict[str, List[str]]:
        """사용자 입력을 기반으로 LLM을 사용하여 동적 쿼리를 생성"""
        logging.info(f"'{country}'의 '{os_type}' 환경에 맞는 동적 쿼리 생성을 시작합니다.")
        
        prompt = f"""
        You are a top-tier cybersecurity analyst creating targeted search queries for a PC optimization tool named 'Grayhound'. Your goal is to identify bloatware for the following environment:
        - Country: {country}
        - Operating System: {os_type}

        **Your Task:**
        Generate two lists of search queries in a single JSON object.

        **1. `known_bloatware_queries`:**
        - List specific, well-known bloatware, Potentially Unwanted Programs (PUPs), or grayware. These are often pre-installed or bundled with other software.
        - If a program name includes 'x86', 'x64', '32bit', or '64bit', also include the name without that part and the other architecture's version (e.g., if you find 'Delfino-x86', add 'Delfino-x64' and 'Delfino').
        - **Good examples for Korea**: Pre-installed banking security software (nProtect, AhnLab), government e-service plugins (Wizvera, MarkAny), unwanted toolbars, and "cleaner" programs that are actually adware.
        - **CRITICAL EXCLUSION RULE**: DO NOT include essential system utilities, hardware drivers (e.g., NVIDIA GeForce Experience, AMD Adrenalin), or major, globally-used software (e.g., KakaoTalk, Microsoft Office, Steam) unless they are infamous for bundling adware.

        **2. `general_search_queries`:**
        - Create exactly 4 high-quality search queries to find IT & CS community discussions about removable programs for the specified environment.
        - Use the dominant language for the specified country.
        - **Source EXCLUSION RULE**: DO NOT target anonymous, unreliable communities known for trolling like 'dcinside.com', 'ilbe.com', '4chan.org', '2ch.sc', '2ch.net', or 'ppomppu.co.kr'.
        - **Preferred Sources**: Prioritize reputable tech journalism sites (e.g., itworld.co.kr), developer communities (e.g., GitHub), or established IT hardware forums (e.g., quasarzone.com, tistory.com, reddit.com).

        **Final Output Instruction:**
        Return ONLY the raw JSON object. Do not wrap it in markdown or add any other text.

        Example for "South Korea" and "Windows 11":
        {{
            "known_bloatware_queries": [
                "nProtect Online Security", "AhnLab Safe Transaction", "Wizvera Veraport", "AnySign4PC", 
                "Crosscert", "CrosscertWeb", "Delfino-x64", "Delfino-x86", "Delfino", "EasyKeytec", 
                "elSP 1.0", "inLINE CrossEx Service", "INISAFE CrossWeb EX", "INISAFE Sandbox", 
                "INISAFE Web", "IPinside LWS Agent", "MarkAny", "Maeps", "MagicLineNP", 
                "SignKorea", "Touchen", "TDSvc", "UbiKey", "VestCert", "XecureWeb"
            ],
            "general_search_queries": [
                "\\"윈도우 11 삭제해도 되는 프로그램\\" site:quasarzone.com", 
                "\\"윈도우 11 클린 설치 후 필수 프로그램\\" site:tistory.com", 
                "\\"windows 11 debloat script\\" site:github.com", 
                "\\"windows 11 debloat list\\" site:reddit.com"
            ]
        }}
        """
        
        response_text = generate_text(prompt, temperature=0.2)
        logging.info("Google AI Studio API response received.")
        
        try:
            # --- ✅ 안정적인 JSON 추출 로직 ---
            # 정규식을 사용하여 응답에서 JSON 객체 부분만 정확히 추출.
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                json_str = match.group(0)
                queries = json.loads(json_str)
                # 로그 출력을 위해 마스킹된 쿼리 사본 생성
                queries_for_log = copy.deepcopy(queries)
                if "known_bloatware_queries" in queries_for_log:
                    queries_for_log["known_bloatware_queries"] = [
                        mask_name(q) for q in queries_for_log["known_bloatware_queries"]
                    ]
                
                # 마스킹된 버전으로 로그 출력
                logging.info(f"Successfully parsed and generated dynamic queries: {queries_for_log}")
                
                # 실제 로직에서는 원본 쿼리 반환
                return queries
            else:
                logging.error(f"Could not find a valid JSON object in the response. Full Response: {response_text}")
                return {}
                
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse the extracted JSON string: {e} - Extracted String: '{json_str}' - Full Response: {response_text}")
            return {}
        except Exception as e:
            logging.error(f"An unexpected error occurred during query generation: {e}")
            return {}
        
    async def evaluate_single_program(self, program_name: str, progress_emitter: Optional[Callable[[str, Any], None]] = None) -> Optional[Dict[str, Any]]:
        """(DB Viewer 상에서) 단일 프로그램명에 대한 구글 검색 및 LLM 평가를 수행하여 블로트웨어 여부를 판단"""
        if not program_name:
            return None
        
        if progress_emitter:
            progress_emitter(f"Searching and evaluating '{mask_name(program_name)}'...", None)
        
        # 1. 구글 검색으로 정보 수집
        search_query = f'"{program_name}"'
        extracted_text = await asyncio.to_thread(
            search_and_extract_text, [search_query], num_results_per_query=3
        )
        
        if not extracted_text:
            if progress_emitter:
                progress_emitter(f"Could not find any information about '{mask_name(program_name)}' from the web.", "error")
            return
        
        if progress_emitter:
           progress_emitter(f"🤖 AI is analyzing the information about '{mask_name(program_name)}'...", None)
        
        # 2. LLM으로 평가
        evaluation_prompt = f"""
        Software Name: "{program_name}"
        The following text was collected from web searches about this software:
        ---
        {extracted_text[:8000]}
        ---
        Please evaluate this software based on the text and provide a risk score and reason in a JSON object.
        - `program_name`: The official name of the program.
        - `risk_score`: An integer score from 0 to 10.
          - 8-10: High-Risk Bloatware (adware, spyware, performance degradation). Strongly recommend removal.
          - 4-7: Common Bloatware/PUP (unnecessary pre-installed software, resource-heavy security plugins). Recommended for removal.
          - 0-3: Legitimate or Essential Software (drivers, system components, well-known applications). MUST NOT be classified as bloatware.
        - `reason`: A brief, specific reason for the risk score based on the text.
        - `generic_name`: A generic name for the program (e.g., "nProtect Online Security Service" -> "nprotect").

        **REASON FIELD RULE**: In the 'reason' field, DO NOT repeat the program's name. Instead, use placeholders like '[This program]' or '[The software]'.
        (Example: Instead of "nProtect is a security module...", write "[This program] is a security module...")

        **CRITICAL**: If the text indicates the program is essential, a driver, or from a major reputable publisher (e.g., 'system32', 'windows', 'explorer.exe', 'svchost.exe', 'wininit.exe', 'lsass.exe', 'services.exe', 'smss.exe', 'csrss.exe', 'winlogon.exe', 'drivers', 'config', 'microsoft', 'nvidia', 'intel', 'amd', 'google', 'system volume information', '$recycle.bin', 'pagefile.sys', 'hiberfil.sys'), assign `risk_score` between 0 and 3. You never need to classify these as bloatware.

        Return only the raw JSON object.
        """
        
        eval_response_text = generate_text(evaluation_prompt, temperature=0.2)

        try:
            match = re.search(r'\{.*\}', eval_response_text, re.DOTALL)
            if match:
                evaluation_data = json.loads(match.group(0))
                # 위험도 4점 이상인 경우에만 유효한 데이터로 간주
                if evaluation_data.get("risk_score", 0) >= 4:
                    evaluation_data["masked_name"] = mask_name(evaluation_data["program_name"])
                    logging.info(f"-> Evaluation completed for '{program_name}': Risk Score {evaluation_data['risk_score']}")
                    if progress_emitter:
                        progress_emitter(f"✅ '{mask_name(program_name)}'이(가) 블로트웨어로 확인되었습니다 (위험도: {evaluation_data['risk_score']}).", "detail")
                    return evaluation_data
                else:
                    logging.info(f"-> Program '{program_name}' is considered safe (Risk Score: {evaluation_data.get('risk_score', 0)}).")
                    if progress_emitter:
                        progress_emitter(f"ℹ️ '{mask_name(program_name)}'은(는) 블로트웨어가 아닌 것으로 판단됩니다.", "detail")
                    return None
        except (json.JSONDecodeError, AttributeError):
            logging.error(f"Failed to parse evaluation for '{program_name}': {eval_response_text}")
            if progress_emitter:
                progress_emitter(f"❌ AI 분석 실패: '{mask_name(program_name)}'", "error")
        return None

    async def scrape_community_info(self, search_queries: Dict[str, List[str]], progress_emitter: Optional[Callable[[str, Any], None]] = None):
        """커뮤니티와 포럼을 검색하여 블로트웨어 정보를 수집하고 AI로 평가 (콜백 추가)"""
        if not search_queries:
            logging.warning("Because the search queries are empty, the scraping process is terminated.")
            if progress_emitter:
                progress_emitter("No search queries provided. Aborting.", "error")
            return
        
        # 1. 텍스트 추출: 커뮤니티 검색 쿼리를 사용하여 텍스트 추출
        logging.info("Start extracting text from community websites...")
        known_bloatware_queries = search_queries.get("known_bloatware_queries", [])
        general_search_queries = search_queries.get("general_search_queries", [])
        all_queries = known_bloatware_queries + general_search_queries
        
        if progress_emitter:
            progress_emitter(f"Starting info collection with {len(all_queries)} queries...", None)
        
        # GoogleSearch_Grayhound 모듈의 함수를 사용하여 텍스트 추출
        extracted_text_blob = await asyncio.to_thread(
            search_and_extract_text, all_queries, num_results_per_query=2
        )

        if not extracted_text_blob:
            if progress_emitter:
                progress_emitter("Could not find any information from the web.", "error")
            return
        if progress_emitter:
            progress_emitter("Text extraction from web complete. Now asking AI to identify candidates...", None)


        # 2. 정보 추출: LLM을 사용해 텍스트에서 프로그램 이름 후보군 추출
        logging.info("Start extracting program names from the collected text using LLM...")
        extraction_prompt = f"""
        Analyze the following text which is collected from various websites about 'programs that can be deleted' or 'bloatware'.
        Extract all potential software or program names.
        Return the result as a single JSON array formatted like this: ["Program Name 1", "Program Name 2", ...].
        Provide only the JSON array in your response.

        --- Text Start ---
        {extracted_text_blob[:15000]}
        --- Text End ---
        """
        response_text = generate_text(extraction_prompt, temperature=0.1)

        try:
            match = re.search(r'\[.*\]', response_text, re.DOTALL)
            program_candidates = json.loads(match.group(0)) if match else []
        except (json.JSONDecodeError, AttributeError):
            logging.error(f"Failed to parse the program name list received from LLM: {response_text}")
            program_candidates = []

        if not program_candidates and not known_bloatware_queries:
            if progress_emitter:
                progress_emitter("AI could not identify any bloatware candidates.", "error")
            return

        # 중복 제거 및 하드코딩된 리스트 추가
        unique_candidates = list(set([p.strip() for p in program_candidates] + known_bloatware_queries))
        logging.info(f"Extracted and combined bloatware candidates ({len(unique_candidates)} items): {unique_candidates[:10]}...")

        if progress_emitter:
            progress_emitter(f"Found {len(unique_candidates)} unique candidates. Starting evaluation...", None)


        # 3. 검증 및 평가: 추출된 후보 프로그램을 심층 분석하고 점수 매기기
        evaluated_programs = []
        for i, program_name in enumerate(unique_candidates):
            if not program_name or len(program_name) > 80: continue

            if progress_emitter:
                # 상세 진행 상태를 클라이언트로 전송
                masked_display_name = mask_name(program_name)
                progress_emitter(f"({i+1}/{len(unique_candidates)}) Evaluating '{masked_display_name}'...", None)

            logging.info(f"Evaluating and scoring candidate program: '{program_name}'")
            evaluation_prompt = f"""
            Software Name: "{program_name}"

            Please evaluate this software and provide a risk score and reason in a JSON object.
            - `program_name`: The official name of the program.
            - `risk_score`: An integer score from 0 to 10.
              - 10: Malicious (Malware, Spyware, Trojan). Demands immediate removal.
              - 8-9: High-Risk Bloatware (Aggressive adware, browser hijackers, keyloggers). Strongly recommend removal.
              - 6-7: Common Bloatware/PUP (Pre-installed software with high resource usage, unwanted toolbars, security software known to cause performance issues). Recommended for removal for system optimization.
              - 4-5: Low-Risk Bloatware (OEM utilities with minor impact, rarely used but safe). User's discretion.
              - 1-3: Legitimate Software (Well-known applications like office suites, browsers, drivers from major vendors). Do not recommend removal.
              - 0: Essential System Component (e.g., from Microsoft for Windows, critical drivers). MUST NOT be removed.
            - `reason`: A brief, specific reason for the risk score. (e.g., "A security module that consumes high resources.", "Adware that displays pop-up ads.", "Required driver component.")
            - `generic_name`: A generic name for the program. (e.g., "INISAFE Web v6.4" → "inisafe", "Delfino-x64" → "delfino", "AnySign For PC(32비트)" → "anysign", "Crosscert" → "crosscert", "nProtect Online Security Service(32비트)" → "nprotect")
          
            **REASON FIELD RULE**: In the 'reason' field, DO NOT repeat the program's name. Instead, use placeholders like '[This program]' or '[The software]'.
            (Example: Instead of "nProtect is a security module...", write "[This program] is a security module...")
          
            **CRITICAL**: If the program is a vital system component (e.g., from Microsoft, NVIDIA, Intel), assign `risk_score` = 0.

            Return only the JSON object.
            {{
                "program_name": "...",
                "risk_score": ...,
                "reason": "..."
                "generic_name": "..."
            }}

            --- Example ---
            {{
                "program_name": "INISAFE Web v6.4",
                "risk_score": 7,
                "reason": "A security module that consumes high resources.",
                "generic_name": "inisafe"
            }}
            """
            eval_response_text = generate_text(evaluation_prompt, temperature=0.3)

            try:
                match = re.search(r'\{.*\}', eval_response_text, re.DOTALL)
                if match:
                    evaluation_data = json.loads(match.group(0))
                    # 위험도 4점 (구버전: 6점 이상) 이상인 경우에만 목록에 추가
                    if evaluation_data.get("risk_score", 0) >= 4:
                        # 마스킹된 이름 추가
                        evaluation_data["masked_name"] = mask_name(evaluation_data["program_name"])
                        evaluated_programs.append(evaluation_data)
                        
                        if progress_emitter:
                            progress_emitter(f" -> ✅ Added '{masked_display_name}' to list (Score: {evaluation_data['risk_score']})", "detail")
                        logging.info(f"-> Evaluation completed: '{program_name}', Risk Score: {evaluation_data['risk_score']}")
                else:
                    if progress_emitter:
                        progress_emitter(f" -> ⚠️ Could not evaluate '{masked_display_name}'. Skipping.", "detail")
                    logging.warning(f"'{program_name}' Evaluation response did not contain a JSON object.")
            except (json.JSONDecodeError, AttributeError):
                if progress_emitter:
                    progress_emitter(f" -> ❌ Failed to parse evaluation for '{masked_display_name}'. Skipping.", "detail")    
                logging.error(f"'{program_name}' Evaluation result parsing failed: {eval_response_text}")

            await asyncio.sleep(1) # API 과부하 방지를 위한 딜레이

        # 4. 평가 완료된 목록을 DB에 저장
        if evaluated_programs:
            if progress_emitter:
                progress_emitter(f"Saving {len(evaluated_programs)} new threats to the database...", None)
            logging.info(f"Saving {len(evaluated_programs)} significant bloatware information to the DB...")
            await database.async_update_threats(evaluated_programs)

    async def run_all_collectors(self, queries: Dict[str, List[str]], progress_emitter: Optional[Callable[[str, Any], None]] = None):
        """모든 정보 수집기를 실행"""
        logging.info("===== Start collecting threat intelligence =====")
        await self.scrape_community_info(queries, progress_emitter)
        logging.info("===== End collecting threat intelligence =====")