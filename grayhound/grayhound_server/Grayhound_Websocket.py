# grayhound_server/Grayhound_Websocket.py
import asyncio
import json
import logging
import sys
import os
import re
import websockets
import signal
import atexit
import time

from typing import Any, List, Dict

# 스크립트가 실행되는 위치를 기준으로 상위 폴더의 경로를 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database
from SecurityAgentManager import SecurityAgentManager
from secure_agent.ThreatIntelligenceCollector import ThreatIntelligenceCollector
from secure_agent.Optimizer import SystemProfiler
from utils import mask_name, mask_name_for_guide

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    stream=sys.stdout
)

# 서버 인스턴스를 전역 변수로 저장
server = None
scan_cache = {}  # 세션별 스캔 결과 캐시

def cleanup_on_exit():
    """프로그램 종료 시 서버를 강제로 종료하고 포트를 해제"""
    global server
    if server:
        try:
            logging.info("프로그램 종료 시 서버 정리 중...")
            # 현재 실행 중인 이벤트 루프가 있다면 사용, 없으면 새로 생성
            try:
                loop = asyncio.get_running_loop()
                if not loop.is_closed():
                    loop.create_task(server.close())
                    loop.create_task(server.wait_closed())
            except RuntimeError:
                # 이벤트 루프가 실행 중이지 않으면 새로 생성
                asyncio.run(server.close())
                asyncio.run(server.wait_closed())
        except Exception as e:
            logging.error(f"종료 시 서버 정리 중 오류: {e}")
        finally:
            server = None

# 프로그램 종료 시 자동으로 정리 함수 등록
atexit.register(cleanup_on_exit)

# --- Websocket 통신 헬퍼 함수 ---
async def emit(websocket, data_type: str, content: Any):
    """클라이언트로 구조화된 JSON을 Websocket을 통해 전송"""
    try:
        message = {"type": data_type, "data": content}
        await websocket.send(json.dumps(message))
    except websockets.exceptions.ConnectionClosed:
        logging.error(f"Client disconnected while emitting message: {data_type}, {content}")
    except Exception as e:
        logging.error(f"Failed to emit message: {e}", exc_info=True)

async def emit_progress(websocket, status: str, details: Any = None):
    """진행 상황을 전송"""
    await emit(websocket, "progress", {"status": status, "details": details})

async def emit_error(websocket, message: str):
    """에러를 전송"""
    await emit(websocket, "error", message)

# --- 워크플로우 함수 ---
async def generate_queries_workflow(websocket, country: str, os_type: str):
    """1단계: DB 업데이트를 위한 검색 쿼리만 생성하여 클라이언트로 전송"""
    try:
        collector = ThreatIntelligenceCollector()
        await emit_progress(websocket, f"Generating optimized search queries for {country} ({os_type})...")
        dynamic_queries = await collector.generate_dynamic_queries(country, os_type)

        if not dynamic_queries:
            await emit_error(websocket, "Failed to generate search queries. Please check the inputs.")
            return

        # 마스킹된 쿼리 생성
        masked_known_queries = [mask_name(q) for q in dynamic_queries.get("known_bloatware_queries", [])]
        
        # 클라이언트에 보낼 데이터 구조 (원본과 마스킹된 버전 모두 포함)
        payload = {
            "original_queries": dynamic_queries,
            "masked_queries": {
                "known_bloatware_queries": masked_known_queries,
                "general_search_queries": dynamic_queries.get("general_search_queries", [])
            }
        }

        # 생성된 쿼리를 'db_queries_generated' 타입으로 전송
        await emit(websocket, "db_queries_generated", payload)

    except Exception as e:
        logging.error(f"An error occurred during query generation: {e}", exc_info=True)
        await emit_error(websocket, f"An unexpected error occurred: {e}")

async def confirm_db_update_workflow(websocket, queries_json: str):
    """2단계: 클라이언트에서 확정된 쿼리로 실제 DB 업데이트 진행"""
    try:
        queries = json.loads(queries_json)
        collector = ThreatIntelligenceCollector()

        # progress_emitter 콜백이 websocket을 통해 메시지를 보내도록 동기 래퍼 함수 사용
        def progress_emitter_callback(status, details):
            # 비동기 함수를 동기적으로 실행
            asyncio.create_task(emit_progress(websocket, status, details))        
        await collector.run_all_collectors(queries, progress_emitter=progress_emitter_callback)
        
        db_count = await database.get_threat_count()
        await emit_progress(websocket, f"✅ DB Update Complete! Currently, {db_count} threats are stored.")
        
        # 완료 후 최신 DB 목록 전송
        full_threat_list = await database.async_get_threats_with_ignore_status("user")
        await emit(websocket, "db_list", full_threat_list)
        
    except json.JSONDecodeError:
        await emit_error(websocket, "Invalid query format received.")
    except Exception as e:
        logging.error(f"An error occurred during DB update: {e}", exc_info=True)
        await emit_error(websocket, f"An unexpected error occurred: {e}")

def _mask_reason_in_db_list(threat_list: List[Dict]) -> List[Dict]:
    """DB 목록에서 reason 필드에 포함된 프로그램명을 마스킹"""
    for threat in threat_list:
        reason = threat.get('reason', '')
        program_name = threat.get('program_name', '')
        generic_name = threat.get('generic_name', '')
        
        # 1. program_name 마스킹
        if program_name:
            escaped_name = re.escape(program_name)
            reason = re.sub(
                escaped_name,
                mask_name(program_name),
                reason,
                flags=re.IGNORECASE
            )
        
        # 2. generic_name이 존재하고, 다른 단어의 일부가 아닐 경우 마스킹
        if generic_name and generic_name != program_name.lower():
            # generic_name은 소문자이므로, 원본 reason에서 실제 매칭된 단어를 찾아 마스킹
            generic_pattern = r'\b' + re.escape(generic_name) + r'\b'
            matches = list(re.finditer(generic_pattern, reason, re.IGNORECASE))
            for match in reversed(matches):
                matched_word = match.group(0)
                start, end = match.span()
                reason = reason[:start] + mask_name(matched_word) + reason[end:]
        
        threat['reason'] = reason
    return threat_list

async def view_db_workflow(websocket):
    """DB 목록 조회 워크플로우"""
    try:
        await emit_progress(websocket, "Fetching bloatware list from the database...")
        full_threat_list = await database.async_get_threats_with_ignore_status("user")
        if not full_threat_list:
            await emit_progress(websocket, "No bloatware found in the database. Please run the DB update first.")
            full_threat_list = [] # 클라이언트에서 null 대신 빈 배열을 받도록 함
        
        # DB 목록에서 reason 필드에 포함된 프로그램명을 마스킹
        masked_threat_list = _mask_reason_in_db_list(full_threat_list) 
        
        await emit(websocket, "db_list", masked_threat_list)
    except Exception as e:
        logging.error(f"An error occurred while fetching DB: {e}", exc_info=True)
        await emit(websocket, "error", f"Failed to fetch database: {e}")
       
async def scan_pc_workflow(websocket, ignored_names_json: str, risk_threshold: int = 4):
    """PC 스캔 워크플로우 (탐지 컨텍스트 캐싱)"""
    try:
        ignored_names = json.loads(ignored_names_json)
        await emit(websocket, "progress", {"status": f"Starting system scan (Risk Threshold: {risk_threshold})...", "data": {"ignored_items": ignored_names}})
        manager = SecurityAgentManager(session_id="grayhound_tauri_session", user_name="user")
        result = await manager.scan_system(ignore_list=ignored_names, risk_threshold=risk_threshold)
        
        if "error" in result:
            await emit(websocket, "error", result["error"])
            return

        threats = result.get("threats", [])
        if not threats:
            await emit(websocket, "progress", {"status": "🎉 Congratulations! No bloatware found to be removed."})
        else:
            # 🔥 탐지 컨텍스트를 포함한 전체 정보 캐싱
            connection_id = id(websocket)
            
            scan_cache[connection_id] = {
                "threats": threats,  # detection_context 포함
                "timestamp": time.time()
            }
            logging.info(f"[CACHE] Stored scan results with detection context for connection {connection_id}: {len(threats)} threats")
        
        await emit(websocket, "scan_result", threats)
    except json.JSONDecodeError:
        await emit(websocket, "error", "Invalid ignore list format received.")
    except Exception as e:
        logging.error(f"An error occurred during PC scan: {e}", exc_info=True)
        await emit(websocket, "error", f"An unexpected error occurred during scan: {e}")

# Phase A 워크플로우: 기본 삭제만 수행
async def phase_a_clean_workflow(websocket, items_to_clean_json: str, language: str = "en"):
    """Phase A: 1단계 기본 정리만 수행"""
    try:
        items_to_clean = json.loads(items_to_clean_json)
        if not items_to_clean:
            await emit_error(websocket, "No items selected for Phase A cleaning.")
            return

        await emit_progress(websocket, f"🧹 Phase A: Starting basic cleanup of {len(items_to_clean)} items...")
        manager = SecurityAgentManager(session_id="grayhound_tauri_session", user_name="user")
        
        # Phase A 전용 cleanup 실행
        cleanup_result = await manager.execute_phase_a_cleanup(items_to_clean, language=language)

        if "error" in cleanup_result:
            await emit_error(websocket, cleanup_result["error"])
            return

        # Phase A 결과 전송
        await emit(websocket, "phase_a_complete", {
            "results": cleanup_result.get("results", []),
            "llm_feedback": cleanup_result.get("llm_feedback", "Phase A completed.")
        })

    except json.JSONDecodeError:
        await emit_error(websocket, "Invalid item list format for Phase A cleaning.")
    except Exception as e:
        logging.error(f"Error during Phase A cleaning: {e}", exc_info=True)
        await emit_error(websocket, f"Phase A error: {e}")

# Phase B 워크플로우: UI 기반 정리
async def phase_b_clean_workflow(websocket, items_to_clean_json: str, language: str = "en"):
    """Phase B: 2단계 UI 기반 정리"""
    try:
        items_to_clean = json.loads(items_to_clean_json)
        if not items_to_clean:
            await emit_error(websocket, "No items selected for Phase B cleaning.")
            return

        await emit_progress(websocket, f"📱 Phase B: Opening Windows Settings for {len(items_to_clean)} items...")
        
        # Optimizer 클라이언트에 직접 연결하여 Phase B 실행
        from agent_client import OptimizerAgentClient
        optimizer_client = OptimizerAgentClient()
        
        # Phase B 전용 cleanup 실행 (개선된 UI 열기)
        phase_b_results = await optimizer_client.execute_phase_b_cleanup(items_to_clean)

        if phase_b_results is None:
            await emit_error(websocket, "Failed to execute Phase B cleanup.")
            return

        # 결과 마스킹 처리 및 자동화 상태 정보 추가
        for result in phase_b_results:
            result["masked_name"] = mask_name(result.get("name", ""))
            result["guide_masked_name"] = mask_name_for_guide(result.get("name", ""))
            
            # Optimizer에서 받은 자동화 상태 정보 유지
            # automated, timeout 등의 필드가 있으면 그대로 전달

        await emit(websocket, "phase_b_complete", {
            "results": phase_b_results
        })

    except json.JSONDecodeError:
        await emit_error(websocket, "Invalid item list format for Phase B cleaning.")
    except Exception as e:
        logging.error(f"Error during Phase B cleaning: {e}", exc_info=True)
        await emit_error(websocket, f"Phase B error: {e}")

# Phase C 워크플로우: 강제 정리
async def phase_c_clean_workflow(websocket, items_to_clean_json: str, language: str = "en"):
    """Phase C: 3단계 강제 정리"""
    try:
        items_to_clean = json.loads(items_to_clean_json)
        if not items_to_clean:
            await emit_error(websocket, "No items selected for Phase C cleaning.")
            return

        await emit_progress(websocket, f"💪 Phase C: Force removing {len(items_to_clean)} items...")
        
        # Optimizer 클라이언트에 직접 연결하여 Phase C 실행
        from agent_client import OptimizerAgentClient
        optimizer_client = OptimizerAgentClient()
        
        # Phase C 전용 cleanup 실행
        phase_c_results = await optimizer_client.execute_phase_c_cleanup(items_to_clean)

        if phase_c_results is None:
            await emit_error(websocket, "Failed to execute Phase C cleanup.")
            return

        # 결과 마스킹 처리
        for result in phase_c_results:
            result["masked_name"] = mask_name(result.get("name", ""))
            result["guide_masked_name"] = mask_name_for_guide(result.get("name", ""))

        await emit(websocket, "phase_c_complete", {
            "results": phase_c_results
        })

    except json.JSONDecodeError:
        await emit_error(websocket, "Invalid item list format for Phase C cleaning.")
    except Exception as e:
        logging.error(f"Error during Phase C cleaning: {e}", exc_info=True)
        await emit_error(websocket, f"Phase C error: {e}")

# 통합된 제거 상태 확인 워크플로우 (개별/전체 모두 처리)
async def check_removal_status_workflow(websocket, program_names_json: str):
    """프로그램들이 실제로 제거되었는지 확인하는 통합 워크플로우 (탐지 컨텍스트 활용)"""
    try:
        # program_names 파싱
        try:
            program_names = json.loads(program_names_json)
            if isinstance(program_names, str):
                program_names = [program_names]
        except json.JSONDecodeError:
            program_names = [program_names_json]
        
        if not program_names:
            await emit_error(websocket, "No programs to check.")
            return

        is_single_check = len(program_names) == 1
        
        if is_single_check:
            await emit_progress(websocket, f"🔍 Checking if {mask_name(program_names[0])} is still installed...")
        else:
            await emit_progress(websocket, f"🔍 Checking removal status for {len(program_names)} programs...")
        
        # 캐시에서 초기 스캔 결과 가져오기
        connection_id = id(websocket)
        cached_data = scan_cache.get(connection_id)
        
        if not cached_data:
            logging.warning(f"[CACHE] No cached scan data found for connection {connection_id}")
            await emit_error(websocket, "No cached scan data found. Please run a scan first.")
            return
        
        logging.info(f"[CACHE] Using cached scan data for connection {connection_id}")
        
        # SecurityAgentManager 인스턴스 생성
        manager = SecurityAgentManager(session_id="grayhound_check_session", user_name="user")
        
        # 현재 시스템 프로파일 생성
        profiler = SystemProfiler()
        current_profile = await profiler.create_system_profile()
        
        # 캐시된 threats에서 프로그램별 탐지 컨텍스트 매핑 생성
        threat_context_map = {}
        for threat in cached_data.get("threats", []):
            threat_context_map[threat["name"]] = threat.get("detection_context")
        
        # 각 프로그램에 대해 제거 상태 확인
        status_results = []
        
        for program_name in program_names:
            # 해당 프로그램의 탐지 컨텍스트 가져오기
            detection_context = threat_context_map.get(program_name)
            
            if not detection_context:
                logging.warning(f"[CACHE] No detection context found for '{mask_name(program_name)}'")
                # 컨텍스트가 없으면 제거된 것으로 간주
                status_results.append({
                    "name": program_name,
                    "masked_name": mask_name(program_name),
                    "status": "removed",
                    "message": f"Successfully removed: {mask_name(program_name)}"
                })
                continue
            
            # 원본 매칭된 threat 정보
            matched_threat = detection_context.get("matched_threat", {})
            program_type = detection_context.get("program_type", "unknown")
            matched_fields = detection_context.get("matched_fields", {})
            
            logging.info(f"[CACHE] Found detection context for '{mask_name(program_name)}': "
                        f"Type={program_type}, DB Program='{mask_name(matched_fields.get('db_program_name', 'Unknown'))}'")
            
            # 프로그램 타입에 따라 다른 검사 수행
            is_still_installed = False
            detection_method = "unknown"
            
            if program_type == "running_process":
                # 프로세스인 경우 현재 실행 중인 프로세스에서 확인
                for proc in current_profile.get("running_processes", []):
                    if proc.get('name', '').lower() == program_name.lower():
                        # 동일한 threat와 매칭되는지 Enhanced 매칭으로 확인
                        is_match, match_reason = manager._enhanced_threat_matching(
                            proc['name'], 
                            matched_threat
                        )
                        if is_match:
                            is_still_installed = True
                            detection_method = match_reason
                            break
            else:
                # 설치된 프로그램인 경우
                for installed_prog in current_profile.get("installed_programs", []):
                    if installed_prog.get('name', '').lower() == program_name.lower():
                        # 동일한 threat와 매칭되는지 Enhanced 매칭으로 확인
                        is_match, match_reason = manager._enhanced_threat_matching(
                            installed_prog['name'], 
                            matched_threat
                        )
                        if is_match:
                            is_still_installed = True
                            detection_method = match_reason
                            break
            
            # 프로그램명이 변경되었을 수 있으므로 전체 프로필에서 threat 매칭 재검사
            if not is_still_installed:
                # 현재 시스템에서 동일한 threat로 탐지되는 항목이 있는지 확인
                all_programs = current_profile.get("installed_programs", []) + current_profile.get("running_processes", [])
                
                for prog in all_programs:
                    is_match, match_reason = manager._enhanced_threat_matching(
                        prog.get('name', ''), 
                        matched_threat
                    )
                    if is_match:
                        is_still_installed = True
                        detection_method = match_reason
                        logging.info(f"[CACHE] Found renamed/variant: '{mask_name(prog.get('name', ''))}' "
                                   f"matches original threat (Method: {match_reason})")
                        break
            
            # 결과 생성
            if is_still_installed:
                # 아직 설치되어 있음
                status_results.append({
                    "name": program_name,
                    "masked_name": mask_name(program_name),
                    "status": "still_exists",
                    "message": f"Still installed: {mask_name(program_name)}",
                    "detection_method": detection_method
                })
                
                if is_single_check:
                    await emit_progress(websocket, f"❌ {mask_name(program_name)} is still installed. Please remove it through Windows Settings.")
                else:
                    await emit_progress(websocket, f"❌ {mask_name(program_name)} is still installed (Detection: {detection_method})")
                
                logging.info(f"[DEBUG] RESULT: STILL INSTALLED - '{mask_name(program_name)}' (Method: {detection_method})")
            else:
                # 제거됨
                status_results.append({
                    "name": program_name,
                    "masked_name": mask_name(program_name),
                    "status": "removed",
                    "message": f"Successfully removed: {mask_name(program_name)}"
                })
                
                if is_single_check:
                    await emit_progress(websocket, f"✅ {mask_name(program_name)} has been successfully removed from your system!")
                else:
                    await emit_progress(websocket, f"✅ {mask_name(program_name)} has been removed.")
                
                logging.info(f"[DEBUG] RESULT: REMOVED - '{mask_name(program_name)}'")
        
        # 결과 요약
        removed_count = sum(1 for r in status_results if r['status'] == 'removed')
        still_installed_count = sum(1 for r in status_results if r['status'] == 'still_exists')
        logging.info(f"[DEBUG] ===== FINAL RESULTS =====")
        logging.info(f"[DEBUG] Removed: {removed_count}, Still installed: {still_installed_count}")
        
        # 결과 전송
        await emit(websocket, "removal_status_checked", {
            "results": status_results,
            "is_single_check": is_single_check
        })
        
    except Exception as e:
        logging.error(f"Error checking removal status: {e}", exc_info=True)
        await emit_error(websocket, f"Failed to check removal status: {e}")

async def generate_final_report_workflow(websocket, cleanup_results_json: str, language: str = "en"):
    """수동 작업 완료 후 최종 리포트 생성 워크플로우"""
    try:
        cleanup_results = json.loads(cleanup_results_json)
        manager = SecurityAgentManager(session_id="grayhound_tauri_session", user_name="user")
        
        # LLM 피드백 생성 (수동 작업 결과 포함)
        llm_feedback = await manager._generate_llm_feedback(cleanup_results, language)
        
        await emit(websocket, "final_report_generated", {
            "llm_feedback": llm_feedback,
            "manual_completed": True
        })
        
    except json.JSONDecodeError:
        await emit_error(websocket, "Invalid cleanup results format.")
    except Exception as e:
        logging.error(f"Error generating final report: {e}", exc_info=True)
        await emit_error(websocket, f"Failed to generate final report: {e}")

async def force_clean_workflow(websocket, items_to_force_clean_json: str, language: str = "en"):
    """강제 정리 워크플로우 - 사용자가 동의한 항목들에 대해서만"""
    try:
        items_to_force_clean = json.loads(items_to_force_clean_json)
        if not items_to_force_clean:
            await emit_error(websocket, "No items selected for force cleaning.")
            return

        await emit_progress(websocket, f"⚠️ Starting FORCEFUL removal of {len(items_to_force_clean)} items...", None)
        manager = SecurityAgentManager(session_id="grayhound_tauri_session", user_name="user")
        
        # 강제 정리를 위한 특별한 실행기 생성 (더 적극적인 설정)
        from agent_client import OptimizerAgentClient
        optimizer_client = OptimizerAgentClient()
        
        # 강제 정리 목록 준비
        force_cleanup_list = []
        for item in items_to_force_clean:
            force_cleanup_list.append({
                "name": item["name"],
                "command_type": "force_uninstall_program",  # 새로운 명령 타입
                "program_name": item["name"]
            })
        
        # 강제 정리 실행
        force_results = await optimizer_client.execute_cleanup_plan(force_cleanup_list)
        
        if force_results is None:
            await emit_error(websocket, "Failed to execute force cleanup.")
            return

        # 결과 정리
        comprehensive_results = []
        for res in force_results:
            original_name = res.get("name")
            res["masked_name"] = mask_name(original_name)
            res["guide_masked_name"] = mask_name_for_guide(original_name)
            comprehensive_results.append(res)
        
        # LLM 피드백 생성
        llm_feedback = await manager._generate_llm_feedback(comprehensive_results, language)

        await emit(websocket, "force_cleanup_complete", {
            "results": comprehensive_results,
            "llm_feedback": llm_feedback
        })

    except json.JSONDecodeError:
        await emit_error(websocket, "Invalid item list format for force cleaning.")
    except Exception as e:
        logging.error(f"An error occurred during force cleaning: {e}", exc_info=True)
        await emit_error(websocket, f"An unexpected error occurred during force cleaning: {e}")

async def open_uninstall_ui_workflow(websocket, program_name: str):
    """Windows 제거 UI 열기 워크플로우"""
    try:
        if not program_name:
            await emit_error(websocket, "No program name provided.")
            return
            
        # SystemExecutor 인스턴스 생성하여 UI 열기 시도
        from SecurityAgentManager import SecurityAgentManager
        manager = SecurityAgentManager(session_id="grayhound_ui_session", user_name="user")
        
        # UI 열기 시도
        ui_result = await manager.open_uninstall_ui(program_name)
        
        if ui_result.get("status") == "ui_opened":
            await emit_progress(websocket, f"✅ Windows uninstall UI opened for '{mask_name(program_name)}'")
            await emit(websocket, "ui_opened_success", {
                "program_name": program_name,
                "masked_name": mask_name(program_name),
                "message": ui_result.get("message", "")
            })
        else:
            await emit_error(websocket, f"Failed to open UI: {ui_result.get('message', 'Unknown error')}")
            
    except Exception as e:
        logging.error(f"Error opening uninstall UI for '{program_name}': {e}", exc_info=True)
        await emit_error(websocket, f"Failed to open uninstall UI: {e}")
        

async def save_ignore_list_workflow(websocket, ignore_list_json: str):
    """클라이언트에서 받은 무시 목록을 DB에 저장"""
    try:
        ignore_list = json.loads(ignore_list_json)
        await database.async_save_ignore_list("user", ignore_list)
        await emit_progress(websocket, "Ignore list saved successfully.")
    except json.JSONDecodeError:
        await emit_error(websocket, "Failed to save ignore list.")
    except Exception as e:
        logging.error(f"An error occurred during ignore list saving: {e}", exc_info=True)
        await emit_error(websocket, f"An unexpected error occurred during ignore list saving: {e}")

# 🚫 DB 추가를 원천적으로 차단할 보호 키워드 목록 (만약의 사태를 위한 안전 장치)
PROTECTED_KEYWORDS = [
    'system32', 'windows', 'explorer.exe', 'svchost.exe', 'wininit.exe',
    'lsass.exe', 'services.exe', 'smss.exe', 'csrss.exe', 'winlogon.exe',
    'drivers', 'config', 'microsoft', 'nvidia', 'intel', 'amd', 'google',
    'system volume information', '$recycle.bin', 'pagefile.sys', 'hiberfil.sys'
]

async def add_item_to_db_workflow(websocket, program_name: str):
    """사용자가 요청한 프로그램을 검증하고 DB에 추가하는 워크플로우"""
    try:
        if not program_name or len(program_name) < 3:
            await emit_error(websocket, "Invalid program name. Please provide a valid program name.")
            return
        
        # 보호 키워드 목록에 포함되어 있는지 확인
        if any(keyword in program_name.lower() for keyword in PROTECTED_KEYWORDS):
            await emit_error(websocket, f"❌ '{program_name}' is a protected keyword and cannot be added to the database.")
            logging.warning(f"❌ '{program_name}' is a protected keyword and cannot be added to the database.")
            return
        
        collector = ThreatIntelligenceCollector()
        
        def progress_emitter_callback(status, details):
            asyncio.create_task(emit_progress(websocket, status, details))
        
        evaluation_result = await collector.evaluate_single_program(program_name, progress_emitter=progress_emitter_callback)
        
        if evaluation_result: # AI가 블로트웨어로 '판단한 경우'에만 실행
            await database.async_add_threat(evaluation_result)
            await emit_progress(websocket, f"✅ '{mask_name(program_name)}' was successfully added to the database. Refreshing the list...")
            await view_db_workflow(websocket) # 성공 후 최신 목록 전송
        elif evaluation_result == "DUPLICATE":
            await emit_progress(websocket, f"❌ '{mask_name(program_name)}' is already in the database.")
        else: # 블로트웨어가 아니거나 평가 실패 시 실행
            await emit_progress(websocket, f"❌ '{mask_name(program_name)}' is not a bloatware and cannot be added to the database.")

    except Exception as e:
        logging.error(f"An error occurred during program evaluation: {e}", exc_info=True)
        await emit_error(websocket, f"An unexpected error occurred during program evaluation: {e}")        

# --- WebSocket 메시지 핸들러 ---
async def handler(websocket):
    """클라이언트와의 WebSocket 통신을 담당하는 메인 핸들러"""
    connection_id = id(websocket)
    logging.info(f"클라이언트 연결됨: {websocket.remote_address} (ID: {connection_id})")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)                
                command = data.get("command")
                args = data.get("args", [])
               
                # 클라이언트에서 받은 명령에 따라 워크플로우 실행
                if command == "update_db":
                    await generate_queries_workflow(websocket, args[0], args[1])
                elif command == "confirm_db_update":
                    await confirm_db_update_workflow(websocket, args[0])
                elif command == "view_db":
                    await view_db_workflow(websocket)
                elif command == "scan":
                    ignored_list = args[0] if args else "[]"
                    risk_thresh = int(args[1]) if len(args) > 1 else 6
                    await scan_pc_workflow(websocket, ignored_list, risk_thresh)
 
                # === Phase 시스템 명령들 ===
                elif command == "phase_a_clean":
                    language_arg = args[1] if len(args) > 1 else "en"
                    await phase_a_clean_workflow(websocket, args[0] if args else "[]", language=language_arg)
                elif command == "phase_b_clean":
                    language_arg = args[1] if len(args) > 1 else "en"
                    await phase_b_clean_workflow(websocket, args[0] if args else "[]", language=language_arg)
                elif command == "phase_c_clean":
                    language_arg = args[1] if len(args) > 1 else "en"
                    await phase_c_clean_workflow(websocket, args[0] if args else "[]", language=language_arg)
                    
                # === 통합된 제거 확인 명령 ===
                elif command == "check_removal_status":
                    await check_removal_status_workflow(websocket, args[0] if args else "[]")
                
                elif command == "force_clean":
                    language_arg = args[1] if len(args) > 1 else "en"
                    await force_clean_workflow(websocket, args[0] if args else "[]", language=language_arg)
                elif command == "open_uninstall_ui":
                    await open_uninstall_ui_workflow(websocket, args[0] if args else "")
                elif command == "generate_final_report":
                    language_arg = args[1] if len(args) > 1 else "en"
                    await generate_final_report_workflow(websocket, args[0] if args else "[]", language=language_arg)
                
                elif command == "save_ignore_list":
                    await save_ignore_list_workflow(websocket, args[0] if args else "[]")
                elif command == "add_item_to_db":
                    await add_item_to_db_workflow(websocket, args[0] if args else "")
                else:
                    logging.error(f"알 수 없는 명령 '{command}' 수신됨.")
                    await emit_error(websocket, f"알 수 없는 명령: {command}")

            except json.JSONDecodeError:
                logging.error(f"잘못된 JSON 형식 수신: {message}")
                await emit_error(websocket, "잘못된 JSON 형식의 메시지입니다.")
            except Exception as e:
                logging.error(f"'{data.get('command')}' 명령 처리 중 오류: {e}", exc_info=True)
                await emit_error(websocket, f"서버 오류 발생: {e}")

    except websockets.exceptions.ConnectionClosed:
        logging.info(f"클라이언트 연결 종료: {websocket.remote_address} (ID: {connection_id})")
    except Exception as e:
        logging.error(f"핸들러에서 심각한 오류 발생: {e}", exc_info=True)
    finally:
        # 🔥 연결 종료 시 캐시 정리
        if connection_id in scan_cache:
            del scan_cache[connection_id]
            logging.info(f"[CACHE] Cleared cache for connection {connection_id}")


async def main():
    """Grayhound WebSocket 서버를 시작합니다."""
    # Optimizer.py가 별도로 실행되고 있다고 가정
    # Grayhound_CLI.py는 이 서버에 접속하는 클라이언트가 됨
    host = "localhost"
    port = 8765  # 클라이언트가 접속할 포트
    global server # 전역 변수로 서버 인스턴스 저장
    try:
        server = await websockets.serve(handler, host, port)
        logging.info(f"🛡️ Grayhound 메인 서버가 ws://{host}:{port} 에서 대기 중...")
        await asyncio.Future()  # 서버를 계속 실행
    except Exception as e:
        logging.error(f"서버 시작 중 오류 발생: {e}")
        if server:
            await server.close()
            await server.wait_closed()
        sys.exit(1)

if __name__ == "__main__":
    if sys.platform == "win32" and sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("사용자 요청으로 서버를 종료합니다. 잘 가! 🤗")
        if server:
            try:
                asyncio.run(server.close())
                asyncio.run(server.wait_closed())
            except Exception as close_error:
                logging.error(f"서버 종료 중 오류: {close_error}")
    except Exception as e:
        logging.error(f"예상치 못한 오류 발생: {e}")
        if server:
            try:
                asyncio.run(server.close())
                asyncio.run(server.wait_closed())
            except Exception as close_error:
                logging.error(f"서버 종료 중 오류: {close_error}")
        sys.exit(1)