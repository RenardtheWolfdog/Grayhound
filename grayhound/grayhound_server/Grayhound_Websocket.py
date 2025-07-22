# grayhound_server/Grayhound_Websocket.py
import asyncio
import json
import logging
import sys
import os
import re
import websockets

from typing import Any, List, Dict

# 스크립트가 실행되는 위치를 기준으로 상위 폴더의 경로를 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database
from SecurityAgentManager import SecurityAgentManager
from secure_agent.ThreatIntelligenceCollector import ThreatIntelligenceCollector
from utils import mask_name

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    stream=sys.stdout
)

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
    """PC 스캔 워크플로우"""
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
        
        await emit(websocket, "scan_result", threats)
    except json.JSONDecodeError:
        await emit(websocket, "error", "Invalid ignore list format received.")
    except Exception as e:
        logging.error(f"An error occurred during PC scan: {e}", exc_info=True)
        await emit(websocket, "error", f"An unexpected error occurred during scan: {e}")

async def clean_pc_workflow(websocket, items_to_clean_json: str, language: str = "en"):
    """PC 정리(삭제) 워크플로우"""
    try:
        items_to_clean = json.loads(items_to_clean_json)
        if not items_to_clean:
            await emit(websocket, "error", "No items selected for cleaning.")
            return

        await emit_progress(websocket, f"Starting to clean {len(items_to_clean)} items...", items_to_clean)
        manager = SecurityAgentManager(session_id="grayhound_tauri_session", user_name="user")
        
        # 클라이언트에서 언어 설정을 받아와서 cleanup 실행
        cleanup_result = await manager.execute_cleanup(items_to_clean, language=language)

        if "error" in cleanup_result:
            await emit(websocket, "error", cleanup_result["error"])
            return

        # 정리 결과와 LLM 리포트를 클라이언트로 전송
        await emit(websocket, "cleanup_complete", {
            "results": cleanup_result.get("results", []),
            "llm_feedback": cleanup_result.get("llm_feedback", "Report generation failed.")
        })

    except json.JSONDecodeError as e:
        await emit_error(websocket, "Invalid item list format received for cleaning.")
    except Exception as e:
        logging.error(f"An error occurred during cleaning: {e}", exc_info=True)
        await emit_error(websocket, f"An unexpected error occurred during cleaning: {e}")

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
    logging.info(f"클라이언트 연결됨: {websocket.remote_address}")
    try:
        async for message in websocket:
            try:
                data = json.loads(message)                
                command = data.get("command")
                args = data.get("args", [])
               
                # # --- 디버깅 로그 ---
                # if command:
                #     logging.info("--- 디버그 시작 ---")
                #     logging.info(f"수신된 command 변수 값: '{command}'")
                #     logging.info(f"command 변수의 타입: {type(command)}")
                #     logging.info(f"command 변수의 바이트(hex) 표현: {command.encode('utf-8').hex()}")
                #     logging.info("---  디버그 종료  ---")
                # # --- 디버깅 로그 끝 ---

                # 클라이언트에서 받은 명령에 따라 워크플로우 실행
                if command == "update_db":
                    await generate_queries_workflow(websocket, args[0], args[1])
                elif command == "confirm_db_update":
                    await confirm_db_update_workflow(websocket, args[0])
                elif command == "view_db":
                    await view_db_workflow(websocket) # websocket 객체 전달
                elif command == "scan":
                    ignored_list = args[0] if args else "[]"
                    risk_thresh = int(args[1]) if len(args) > 1 else 6 # 기본값 6
                    await scan_pc_workflow(websocket, ignored_list, risk_thresh)
                elif command == "clean":
                    # 클라이언트에서 받은 language 인자 사용
                    language_arg = args[1] if len(args) > 1 else "en"
                    await clean_pc_workflow(websocket, args[0] if args else "[]", language=language_arg)
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
                # 어떤 명령 처리 중 오류가 났는지 로깅
                logging.error(f"'{data.get('command')}' 명령 처리 중 오류: {e}", exc_info=True)
                await emit_error(websocket, f"서버 오류 발생: {e}")

    except websockets.exceptions.ConnectionClosed:
        logging.info(f"클라이언트 연결 종료: {websocket.remote_address}")
    except Exception as e:
        logging.error(f"핸들러에서 심각한 오류 발생: {e}", exc_info=True)


async def main():
    """Grayhound WebSocket 서버를 시작합니다."""
    # Optimizer.py가 별도로 실행되고 있다고 가정
    # Grayhound_CLI.py는 이 서버에 접속하는 클라이언트가 됨
    host = "localhost"
    port = 8765  # 클라이언트가 접속할 포트
    async with websockets.serve(handler, host, port):
        logging.info(f"🛡️ Grayhound 메인 서버가 ws://{host}:{port} 에서 대기 중...")
        await asyncio.Future()  # 서버를 계속 실행

if __name__ == "__main__":
    if sys.platform == "win32" and sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())