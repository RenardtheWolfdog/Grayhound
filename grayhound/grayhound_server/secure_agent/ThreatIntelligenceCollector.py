# secure_agent/ThreatIntelligenceCollector.py
# Grayhound's Two-Phase Threat Intelligence Collector Module

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

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import mask_name

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(module)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class ThreatIntelligenceCollector:
    """외부 정보원으로부터 위협 인텔리전스를 수집, 분석하고 DB에 저장"""
    """Two-Phase 위협 인텔리전스 수집기: 1차 기본정보 수집 → 2차 상세정보 보강"""

    def _extract_brand_keywords(self, program_name: str, publisher: str = "") -> List[str]:
        """프로그램명과 게시자명에서 브랜드 키워드를 추출"""
        keywords = set()
        
        # 프로그램명에서 키워드 추출
        if program_name:
            # 공백, 하이픈, 언더스코어로 분리
            words = re.split(r'[\s\-_]+', program_name.lower())
            for word in words:
                # 버전 번호, 비트 정보 제거
                clean_word = re.sub(r'(x86|x64|32bit|64bit|32비트|64비트|v?\d+\.?\d*)', '', word)
                if len(clean_word) >= 3:  # 3글자 이상만 키워드로 사용
                    keywords.add(clean_word)
        
        # 게시자명에서 키워드 추출
        if publisher:
            pub_words = re.split(r'[\s\-_\.]+', publisher.lower())
            for word in pub_words:
                clean_word = re.sub(r'(inc|corp|corporation|ltd|limited|co|company)', '', word)
                if len(clean_word) >= 3:
                    keywords.add(clean_word)
        
        # 불용어 제거
        stopwords = {'the', 'and', 'for', 'with', 'software', 'program', 'application', 'app', 'tool', 'suite', 'service', 'system', 'windows', 'microsoft'}
        keywords = keywords - stopwords
        
        return list(keywords)

    async def generate_dynamic_queries(self, country: str, os_type: str) -> Dict[str, List[str]]:
        """1단계: 사용자 입력을 기반으로 LLM을 사용하여 동적 쿼리를 생성"""
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

        --- EXAMPLES ---

        **Example for "South Korea" and "Windows 11":**
        {{
            "known_bloatware_queries": [
                "nProtect Online Security", "AhnLab Safe Transaction", "Wizvera Veraport", "AnySign4PC", 
                "Crosscert", "CrosscertWeb", "Delfino-x64", "Delfino-x86", "Delfino", "EasyKeytec", 
                "elSP 1.0", "inLINE CrossEx Service", "INISAFE CrossWeb EX", "INISAFE Sandbox", 
                "INISAFE Web", "IPinside LWS Agent", "MarkAny", "Maeps", "MagicLineNP", 
                "SignKorea", "Touchen", "TDSvc", "UbiKey", "VestCert", "XecureWeb", "Alyac", "Altools", "ESTsoft", "McAfee", "Norton"
            ],
            "general_search_queries": [
                "\\"윈도우 11 삭제해도 되는 프로그램\\" site:quasarzone.com", 
                "\\"windows 11 debloat script\\" site:github.com",
                "\\"윈도우 11 삭제해도 되는 프로그램\\" site:tistory.com",
                "\\"windows 11 bloatware list\\" site:reddit.com"
            ]
        }}

        **Example for "USA" and "Windows 11":**
        {{
            "known_bloatware_queries": ["McAfee WebAdvisor", "Norton Security", "CCleaner", "BonziBuddy", "WeatherBug", "MyWebSearch", "Ask Toolbar"],
            "general_search_queries": [
                "\\"windows 11 remove bloatware\\" site:reddit.com",
                "\\"pre-installed apps to uninstall windows 11\\" site:howtogeek.com",
                "\\"windows 11 debloat script\\" site:github.com",
                "\\"best pc cleaner\\" site:pcmag.com"
            ]
        }}

        **Example for "Japan" and "Windows 11":**
        {{
            "known_bloatware_queries": ["Baidu IME", "Hao 123", "RegClean Pro", "KINGSOFT Internet Security", "WinZip Driver Updater", "マカフィー リブセーフ (McAfee LiveSafe)"],
            "general_search_queries": [
                "\\"windows 11 不要なプリインストールソフト\\" site:hatenablog.com",
                "\\"windows 11 削除してはいけないプログラム\\" site:yahoo.co.jp",
                "\\"windows 11 デブロット\\" site:github.com",
                "\\"PC 高速化\\" site:pc.watch.impress.co.jp"
            ]
        }}

        **Example for "China" and "Windows 11":**
        {{
            "known_bloatware_queries": ["Baidu Antivirus (百度杀毒)", "360 Total Security (360安全卫士)", "Kingsoft PC Doctor (金山毒霸)", "Tencent PC Manager (腾讯电脑管家)", "2345.com", "Hao123"],
            "general_search_queries": [
                "\\"windows 11 预装软件卸载\\" site:zhihu.com",
                "\\"win11 精简 脚本\\" site:gitee.com",
                "\\"可以卸载的windows程序\\" site:v2ex.com",
                "\\"windows 11 C盘清理\\" site:weibo.com"
            ]
        }}

        **Example for "India" and "Windows 11":**
        {{
            "known_bloatware_queries": ["Glary Utilities", "Advanced SystemCare", "Driver Booster", "Hola VPN", "MAPit", "AppLock"],
            "general_search_queries": [
                "\\"windows 11 bloatware to remove india\\" site:reddit.com",
                "\\"how to speed up windows 11 laptop\\" site:gadgets360.com",
                "\\"debloat windows 11 script\\" site:github.com",
                "\\"best free pc optimizer india\\" site:digit.in"
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
        
    async def _enhance_threat_metadata(self, basic_threat_data: Dict[str, Any]) -> Dict[str, Any]:
        """2단계: 기본 정보를 보강하여 위협 메타데이터 생성"""
        program_name = basic_threat_data['program_name']
        
        if not program_name:
            return basic_threat_data
        
        logging.info(f"Enhancing metadata for '{program_name}'...")
        
        # 상세 정보 수집을 위한 프롬프트
        enhancement_prompt = f"""
        Software Name: "{program_name}"
        Current Basic Info: {json.dumps(basic_threat_data, ensure_ascii=False)}

        Please enhance this bloatware/PUP information with additional metadata. Based on your knowledge of this software, provide the following additional fields:

        **Required Additional Fields:**
        - `publisher`: The publisher/company name (if known, otherwise leave empty)
        - `brand_keywords`: An array of 2-4 brand-related keywords that could help identify variants of this software
        - `alternative_names`: An array of alternative names or variants (if known, otherwise leave empty)
        - `process_names`: Likely process names (educated guess based on program name, e.g., "alyac.exe,alyacservice.exe")

        **BRAND KEYWORDS RULE**: Extract 2-4 distinctive keywords that represent the brand/company. For example:
        - "ALYAC" -> ["alyac", "estsoft"] (if you know ESTsoft is the publisher)
        - "CCleaner" -> ["ccleaner", "piriform"]
        - "Norton Security" -> ["norton", "symantec"]

        **PROCESS NAMES RULE**: Generate educated guesses for likely process names:
        - Use the generic name + .exe
        - Add common variations like service, gui, updater
        - Example: "alyac" -> "alyac.exe,alyacservice.exe,alyacgui.exe"

        **IMPORTANT**: If you don't know specific information, leave those fields empty rather than guessing incorrectly.

        Return the COMPLETE enhanced JSON object with all original fields plus the new fields.

        Example:
        {{
            "program_name": "ALYAC",
            "risk_score": 4,
            "reason": "[This program] is a Korean antivirus that consumes high system resources and is often pre-installed.",
            "generic_name": "alyac",
            "publisher": "ESTsoft",
            "brand_keywords": ["alyac", "estsoft"],
            "alternative_names": ["ALYAC Internet Security", "알약"],
            "process_names": "alyac.exe,alyacservice.exe,alyacgui.exe"
        }}
        """
        
        response_text = generate_text(enhancement_prompt, temperature=0.1)
        
        try:
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                enhanced_data = json.loads(match.group(0))
                
                # 브랜드 키워드가 없거나 비어있으면 자동 생성
                if not enhanced_data.get("brand_keywords"):
                    enhanced_data["brand_keywords"] = self._extract_brand_keywords(
                        enhanced_data.get("program_name", ""), 
                        enhanced_data.get("publisher", "")
                    )
                
                logging.info(f"Successfully enhanced metadata for '{program_name}'")
                return enhanced_data
            else:
                logging.warning(f"Could not enhance metadata for '{program_name}'. Using basic data.")
                return basic_threat_data
                
        except (json.JSONDecodeError, AttributeError) as e:
            logging.error(f"Failed to parse enhanced metadata for '{program_name}': {e}")
            return basic_threat_data        
        
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
        
        # 2. 1차 기본 평가
        basic_evaluation_prompt = f"""
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

        **CRITICAL**: If the text indicates the program is essential, a driver, or from a major reputable publisher, assign `risk_score` between 0 and 3.

        Return only the raw JSON object.
        """
        
        eval_response_text = generate_text(basic_evaluation_prompt, temperature=0.2)

        try:
            match = re.search(r'\{.*\}', eval_response_text, re.DOTALL)
            if match:
                basic_evaluation_data = json.loads(match.group(0))
                
                # 위험도 4점 이상인 경우에만 진행
                if basic_evaluation_data.get("risk_score", 0) >= 4:
                    # 3. 2차 메타데이터 보강
                    if progress_emitter:
                        progress_emitter(f"🔍 Enhancing metadata for '{mask_name(program_name)}'...", None)
                    
                    enhanced_data = await self._enhance_threat_metadata(basic_evaluation_data)
                    enhanced_data["masked_name"] = mask_name(enhanced_data["program_name"])
                    
                    logging.info(f"-> Enhanced evaluation completed for '{mask_name(program_name)}': Risk Score {enhanced_data['risk_score']}")
                    if progress_emitter:
                        progress_emitter(f"✅ '{mask_name(program_name)}' is considered as bloatware (Risk Score: {enhanced_data['risk_score']}).", "detail")
                    return enhanced_data
                else:
                    logging.info(f"-> Program '{program_name}' is considered safe (Risk Score: {basic_evaluation_data.get('risk_score', 0)}).")
                    if progress_emitter:
                        progress_emitter(f"ℹ️ '{mask_name(program_name)}' is considered as safe.", "detail")
                    return None
        except (json.JSONDecodeError, AttributeError):
            logging.error(f"Failed to parse evaluation for '{program_name}': {eval_response_text}")
            if progress_emitter:
                progress_emitter(f"❌ AI analysis failed for '{mask_name(program_name)}'", "error")
        return None
    
    async def scrape_community_info(self, search_queries: Dict[str, List[str]], progress_emitter: Optional[Callable[[str, Any], None]] = None):
        """커뮤니티와 포럼을 검색하여 블로트웨어 정보를 수집하고 AI로 평가 (콜백 추가)
        - Known bloatware 중심으로 정보를 수집하고 AI로 평가"""
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

        # 3. Two-Phase 평가: 1차 기본평가 → 2차 메타데이터 보강
        evaluated_programs = []
        for i, program_name in enumerate(unique_candidates):
            if not program_name or len(program_name) > 80: continue

            if progress_emitter:
                masked_display_name = mask_name(program_name)
                progress_emitter(f"({i+1}/{len(unique_candidates)}) Phase 1: Evaluating '{masked_display_name}'...", None)

            logging.info(f"Phase 1: Basic evaluation for '{program_name}'")
            
            # Phase 1: 기본 평가
            basic_evaluation_prompt = f"""
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
            - `reason`: A brief, specific reason for the risk score.
            - `generic_name`: A generic name for the program.
          
            **REASON FIELD RULE**: In the 'reason' field, DO NOT repeat the program's name. Instead, use placeholders like '[This program]' or '[The software]'.
          
            **CRITICAL**: If the program is a vital system component, assign `risk_score` = 0.

            Return only the JSON object.
            """
            
            basic_response_text = generate_text(basic_evaluation_prompt, temperature=0.3)

            try:
                match = re.search(r'\{.*\}', basic_response_text, re.DOTALL)
                if match:
                    basic_data = json.loads(match.group(0))
                    
                    # 위험도 4점 이상인 경우에만 Phase 2 진행
                    if basic_data.get("risk_score", 0) >= 4:
                        if progress_emitter:
                            progress_emitter(f"({i+1}/{len(unique_candidates)}) Phase 2: Enhancing '{masked_display_name}'...", None)
                        
                        # Phase 2: 메타데이터 보강
                        enhanced_data = await self._enhance_threat_metadata(basic_data)
                        enhanced_data["masked_name"] = mask_name(enhanced_data["program_name"])
                        
                        evaluated_programs.append(enhanced_data)
                        
                        if progress_emitter:
                            progress_emitter(f" -> ✅ Added '{masked_display_name}' to list (Score: {enhanced_data['risk_score']})", "detail")
                        logging.info(f"-> Two-phase evaluation completed: '{program_name}', Risk Score: {enhanced_data['risk_score']}")
                else:
                    if progress_emitter:
                        progress_emitter(f" -> ⚠️ Could not evaluate '{masked_display_name}'. Skipping.", "detail")
                    logging.warning(f"'{program_name}' Evaluation response did not contain a JSON object.")
            except (json.JSONDecodeError, AttributeError):
                if progress_emitter:
                    progress_emitter(f" -> ❌ Failed to parse evaluation for '{masked_display_name}'. Skipping.", "detail")    
                logging.error(f"'{program_name}' Evaluation result parsing failed: {basic_response_text}")

            await asyncio.sleep(1)

        # 4. 평가 완료된 목록을 DB에 저장
        if evaluated_programs:
            if progress_emitter:
                progress_emitter(f"Saving {len(evaluated_programs)} enhanced threats to the database...", None)
            logging.info(f"Saving {len(evaluated_programs)} enhanced bloatware information to the DB...")
            await database.async_update_threats(evaluated_programs)

    async def run_all_collectors(self, queries: Dict[str, List[str]], progress_emitter: Optional[Callable[[str, Any], None]] = None):
        """모든 정보 수집기를 실행"""
        logging.info("===== Start Two-Phase Threat Intelligence Collection =====")
        await self.scrape_community_info(queries, progress_emitter)
        logging.info("===== End Two-Phase Threat Intelligence Collection =====")