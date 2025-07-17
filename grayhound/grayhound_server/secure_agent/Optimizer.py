# Optimizer.py (v2.2 - Robust Executor)
# Grayhound's Local System Scout & Executor Agent

import asyncio
import logging
import os
import shutil
import psutil
import winreg
import subprocess
import json
import websockets
from typing import Optional, Dict, Any, List, Tuple

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- 기본 설정 ---
HOST = 'localhost'
PORT = 9001

# --- 시스템 프로파일러 클래스 ---
class SystemProfiler:
    """시스템의 상세 프로필을 생성하여 분석을 위해 중앙 서버로 전송"""
    def __init__(self):
        self.profile = {}
        logging.info("시스템 프로파일러 초기화. 정보 수집을 시작할게! *킁킁...🐺*")

    def get_installed_programs(self) -> List[Dict[str, Any]]:
        """Windows 레지스트리를 통해 설치된 프로그램 목록을 가져옴"""
        programs = []
        uninstall_paths = [
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
            r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        ]
        for path in uninstall_paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        sub_key_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, sub_key_name) as sub_key:
                            try:
                                name = winreg.QueryValueEx(sub_key, "DisplayName")[0]
                                version = winreg.QueryValueEx(sub_key, "DisplayVersion")[0]
                                publisher = winreg.QueryValueEx(sub_key, "Publisher")[0]
                                try:
                                    install_location = winreg.QueryValueEx(sub_key, "InstallLocation")[0]
                                except OSError:
                                    install_location = "N/A"
                                programs.append({
                                    "name": name, "version": version,
                                    "publisher": publisher, "install_location": install_location
                                })
                            except OSError:
                                continue
            except FileNotFoundError:
                continue
        logging.info(f"{len(programs)}개의 설치된 프로그램을 발견했어! 🐾")
        return programs

    def get_running_processes(self) -> List[Dict[str, Any]]:
        """현재 실행 중인 모든 프로세스의 상세 정보를 가져옴"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'username']):
            try:
                processes.append({
                    "pid": proc.info['pid'], "name": proc.info['name'],
                    "path": proc.info['exe'], "username": proc.info['username']
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        logging.info(f"{len(processes)}개의 실행 중인 프로세스를 발견했어! 🐾")
        return processes

    async def create_system_profile(self) -> Dict[str, Any]:
        """시스템의 전체 프로필을 JSON 객체로 생성"""
        logging.info("시스템 전체 프로필 생성을 시작할게... 🌒")
        programs_task = asyncio.to_thread(self.get_installed_programs)
        processes_task = asyncio.to_thread(self.get_running_processes)
        installed_programs, running_processes = await asyncio.gather(programs_task, processes_task)
        self.profile = {
            "installed_programs": installed_programs,
            "running_processes": running_processes,
        }
        logging.info("시스템 프로필 생성 완료! 🌝")
        return self.profile

# --- 시스템 실행기 클래스 (Executor의 역할) ---
class SystemExecutor:
    """사용자의 최종 명령에 따라 시스템 정리 작업을 수행"""
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.protected_paths = [
            os.environ.get("SystemRoot", "C:\\Windows").lower(),
            os.environ.get("UserProfile", "").lower(),
        ]
        self.protected_publishers = [
            "microsoft corporation", "microsoft", "nvidia corporation", "intel corporation", 
            "amd", "advanced micro devices, inc.", "google llc", "google inc."
        ]
        logging.info(f"시스템 실행기 초기화. **Dry Run Mode: {self.dry_run}**")
        if self.dry_run:
            logging.warning("Dry Run 모드에서는 실제 파일 삭제나 프로세스 종료가 이루어지지 않아!")

    def terminate_process(self, pid: int) -> Dict[str, Any]:
        """PID를 사용하여 프로세스를 종료"""
        try:
            p = psutil.Process(pid)
            proc_name = p.name()
            if self.dry_run:
                logging.info(f"[Dry Run] 프로세스 종료 시도: PID={pid}, Name={proc_name}")
                return {"status": "success", "message": f"'{proc_name}' 프로세스를 종료하는 시늉만 했습니다."}
            p.terminate()
            p.wait(timeout=3)
            return {"status": "success", "message": f"'{proc_name}' 프로세스를 성공적으로 종료했습니다."}
        except psutil.NoSuchProcess:
            return {"status": "failure", "message": "프로세스가 이미 종료되었습니다."}
        except psutil.TimeoutExpired:
            p.kill()
            return {"status": "success", "message": f"'{p.name()}' 프로세스를 강제로 종료했습니다."}
        except Exception as e:
            return {"status": "failure", "message": str(e)}

    def delete_path(self, path: str) -> Dict[str, Any]:
        """파일 또는 폴더 경로를 삭제"""
        try:
            if not os.path.exists(path):
                return {"status": "failure", "message": "경로가 존재하지 않습니다."}
            normalized_path = os.path.normpath(path).lower()
            if any(normalized_path.startswith(p) for p in self.protected_paths if p):
                return {"status": "failure", "message": f"보호된 경로 '{os.path.basename(path)}'는 삭제할 수 없습니다."}
            
            if self.dry_run:
                logging.info(f"[Dry Run] 경로 삭제 시도: {path}")
                return {"status": "success", "message": f"'{os.path.basename(path)}' 경로를 삭제하는 척만 했습니다."}
            
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return {"status": "success", "message": f"'{os.path.basename(path)}' 경로를 성공적으로 삭제했습니다."}
        except Exception as e:
            return {"status": "failure", "message": str(e)}

    def get_uninstall_command(self, program_name: str) -> Tuple[Optional[str], Optional[str]]:
        """프로그램 이름으로 UninstallString과 게시자를 찾아 반환"""
        uninstall_paths = [
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
            r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        ]
        for path in uninstall_paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        sub_key_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, sub_key_name) as sub_key:
                            try:
                                name = winreg.QueryValueEx(sub_key, "DisplayName")[0]
                                if name.lower() == program_name.lower():
                                    uninstall_string = winreg.QueryValueEx(sub_key, "UninstallString")[0]
                                    publisher = winreg.QueryValueEx(sub_key, "Publisher")[0]
                                    if 'msiexec.exe' in uninstall_string.lower() and '/qn' not in uninstall_string.lower():
                                        uninstall_string = uninstall_string.replace('/I', '/X').replace('/i', '/x') + ' /qn'
                                    return uninstall_string, publisher
                            except OSError:
                                continue
            except FileNotFoundError:
                continue
        return None, None

    def uninstall_program(self, program_name: str) -> Dict[str, Any]:
        """프로그램의 UninstallString을 찾아 제거를 시도하고 결과를 dict로 반환"""
        uninstall_command, publisher = self.get_uninstall_command(program_name)
        if not uninstall_command:
            return {"status": "failure", "message": f"'{program_name}'의 제거 정보를 찾을 수 없습니다."}
        
        if publisher and publisher.lower() in self.protected_publishers:
            return {"status": "failure", "message": f"'{program_name}'는 보호된 게시자의 프로그램이라 제거할 수 없습니다."}
        
        if self.dry_run:
            return {"status": "success", "message": f"'{program_name}' 프로그램을 제거하는 시늉만 했습니다."}
        
        try:
            logging.info(f"프로그램 제거 실행: {uninstall_command}")
            subprocess.run(uninstall_command, check=True, shell=True, capture_output=True, text=True, startupinfo=subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW))
            return {"status": "success", "message": f"'{program_name}' 프로그램을 성공적으로 제거했습니다."}
        except subprocess.CalledProcessError as e:
            return {"status": "failure", "message": f"'{program_name}' 프로그램 제거에 실패했습니다: {e.stderr}"}
        except Exception as e:
            return {"status": "failure", "message": f"'{program_name}' 프로그램 제거 중 오류가 발생했습니다."}

    async def execute_cleanup(self, cleanup_list: List[Dict]) -> List[Dict]:
        """정리 목록을 받아 순차적으로 작업 수행하고 구조화된 결과 반환"""
        final_results = []
        
        # 1. PID가 있는 항목(실행 중인 프로세스) 먼저 종료
        pids_to_terminate = [item['pid'] for item in cleanup_list if item.get('pid')]
        for item in cleanup_list:
            if item.get('pid'):
                logging.info(f"프로세스 종료 시도: PID {item['pid']}, 이름: {item['name']}")
                result_details = self.terminate_process(item['pid'])
                final_results.append({
                    "name": item.get("name"),
                    "status": result_details.get("status"),
                    "message": result_details.get("message")
                })
        
        # 2. 프로그램 제거 시도
        for item in cleanup_list:
            if item.get('command_type') == 'uninstall_program':
                # 프로세스가 이미 종료되었을 수 있으므로 잠시 대기
                await asyncio.sleep(0.5) 
                logging.info(f"프로그램 제거 시도: {item['program_name']}")
                result_details = await asyncio.to_thread(self.uninstall_program, item["program_name"])
                final_results.append({
                    "name": item.get("name"),
                    "status": result_details.get("status"),
                    "message": result_details.get("message")
                })

        return final_results

async def handler(websocket):
    """클라이언트(Grayhound_CLI)와의 통신을 담당하는 핸들러"""
    logging.info(f"지휘 본부 연결됨 🐺🐾: {websocket.remote_address}")
    try:
        async for message in websocket:
            data = json.loads(message)
            command = data.get("command")
            logging.info(f"명령 수신 🐾: {command}")

            if command == "profile_system":
                profiler = SystemProfiler()
                system_profile = await profiler.create_system_profile()
                response = {"type": "system_profile_data", "data": system_profile}
                await websocket.send(json.dumps(response))
                logging.info("시스템 프로필 데이터를 지휘 본부로 전송 완료 🐾.")

            elif command == "cleanup":
                cleanup_list = data.get("list", [])
                logging.info(f"{len(cleanup_list)}개 항목에 대한 정리 작업 시작 🐾.")
                executor = SystemExecutor(dry_run=False)
                cleanup_results = await executor.execute_cleanup(cleanup_list)
                response = {"type": "cleanup_result", "data": cleanup_results}
                await websocket.send(json.dumps(response))
                logging.info("정리 작업 완료 및 결과 전송 🐾.")

    except websockets.exceptions.ConnectionClosed:
        logging.info(f"지휘 본부 연결 종료 🐾: {websocket.remote_address}")
    except Exception as e:
        logging.error(f"핸들러 오류 발생 🐾: {e}", exc_info=True)
        error_response = {"type": "error", "message": str(e)}
        await websocket.send(json.dumps(error_response))

async def main():
    """WebSocket 서버를 시작하는 메인 함수"""
    async with websockets.serve(handler, HOST, PORT):
        logging.info(f"정찰병 늑대 에이전트가 {HOST}:{PORT}에서 대기 중... 아우~ 🐺🐾")
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("사용자 요청으로 서버를 종료합니다. 잘 가! 🤗")