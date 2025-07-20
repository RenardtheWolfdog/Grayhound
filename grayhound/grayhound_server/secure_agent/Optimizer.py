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
import time

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import mask_name

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
    """사용자의 최종 명령에 따라 시스템 정리 작업을 수행 (강제 제거 기능 포함)"""
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
                logging.info(f"[Dry Run] 프로세스 종료 시도: PID={pid}, Name={mask_name(proc_name)}")
                return {"status": "success", "message": f"'{mask_name(proc_name)}' 프로세스를 종료하는 시늉만 했어! 🐾"}
            p.terminate()
            p.wait(timeout=3)
            return {"status": "success", "message": f"'{mask_name(proc_name)}' 프로세스를 성공적으로 종료했어! 🐾"}
        except psutil.NoSuchProcess:
            return {"status": "failure", "message": "프로세스가 이미 종료되었어! 🐾"}
        except psutil.TimeoutExpired:
            p.kill()
            return {"status": "success", "message": f"'{mask_name(p.name())}' 프로세스를 강제로 종료했어! 🐾"}
        except Exception as e:
            return {"status": "failure", "message": str(e)}

    def delete_path(self, path: str) -> Dict[str, Any]:
        """파일 또는 폴더 경로를 삭제"""
        try:
            if not os.path.exists(path):
                return {"status": "failure", "message": "경로가 존재하지 않아! 🐾"}
            normalized_path = os.path.normpath(path).lower()
            if any(normalized_path.startswith(p) for p in self.protected_paths if p):
                return {"status": "failure", "message": f"보호된 경로 '{mask_name(os.path.basename(path))}'는 삭제할 수 없어! 🐾"}
            
            if self.dry_run:
                logging.info(f"[Dry Run] 경로 삭제 시도: {mask_name(path)}")
                return {"status": "success", "message": f"'{mask_name(os.path.basename(path))}' 경로를 삭제하는 척만 했어! 🐾"}
            
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return {"status": "success", "message": f"'{mask_name(os.path.basename(path))}' 경로를 성공적으로 삭제했어! 🐾"}
        except Exception as e:
            return {"status": "failure", "message": str(e)}

    def _delete_key_recursively(self, root_key_handle: Any, sub_key_to_delete: str, full_key_path_str: str, cleaned_entries: List[str]) -> None:
        """지정된 레지스트리 키와 모든 하위 키를 재귀적으로 삭제 (경로 문자열 전달 방식)"""
        try:
            # 삭제할 대상 키를 열어 하위 키들을 먼저 처리
            with winreg.OpenKey(root_key_handle, sub_key_to_delete) as current_key_handle:
                sub_key_names = []
                try:
                    i = 0
                    while True:
                        sub_key_names.append(winreg.EnumKey(current_key_handle, i))
                        i += 1
                except OSError: # 더 이상 하위 키가 없을 때까지 반복
                    pass
                
                # 모든 하위 키에 대해 재귀적으로 삭제 함수를 호출함
                for name in sub_key_names:
                    self._delete_key_recursively(current_key_handle, name, f"{full_key_path_str}\\{name}", cleaned_entries)
                
            # 모든 하위 키가 삭제된 후 현재 키를 삭제
            winreg.DeleteKey(root_key_handle, sub_key_to_delete)
            cleaned_entries.append(full_key_path_str)
            logging.info(f"Removed registry key: {full_key_path_str}")
            
        except FileNotFoundError:
            pass # 키가 이미 없으면 정상이므로 통과
        except OSError as e:
            logging.warning(f"Failed to remove registry key {full_key_path_str}: {e}")

    def _cleanup_software_keys(self, program_name: str, publisher: str, cleaned_entries: List[str]):
        """HKCU와 HKLM의 Software 경로에서 프로그램/게시자 관련 키를 찾아 삭제"""
        logging.info(f"Searching for '{mask_name(program_name)}' and '{mask_name(publisher)}' in Software registry keys...")
        
        # HKEY 정수 값을 문자열로 매핑하기 위한 딕셔너리
        HKEY_MAP = {
            winreg.HKEY_CURRENT_USER: "HKEY_CURRENT_USER",
            winreg.HKEY_LOCAL_MACHINE: "HKEY_LOCAL_MACHINE",
        }
        
        search_locations = [
            (winreg.HKEY_CURRENT_USER, r"Software"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node") # 64비트 시스템의 32비트 프로그램
        ]

        # 검색할 키워드 (소문자로 변환하여 비교)
        keywords = {kw.lower() for kw in [program_name, publisher] if kw}
        if not keywords: return

        for root_hkey, base_path in search_locations:
            try:
                with winreg.OpenKey(root_hkey, base_path) as base_key_handle:
                    keys_to_delete = []
                    try:
                        i = 0
                        while True:
                            sub_key_name = winreg.EnumKey(base_key_handle, i)
                            # 키워드 중 하나라도 포함되면 삭제 목록에 추가
                            if any(keyword in sub_key_name.lower() for keyword in keywords):
                                keys_to_delete.append(sub_key_name)
                            i += 1
                    except OSError:
                        pass # 더 이상 하위 키가 없음

                    # 찾은 키들에 대해 실제 삭제 작업 수행
                    for key_name in keys_to_delete:
                        root_name = HKEY_MAP.get(root_hkey, "Unknown_HKEY")
                        full_key_path = f"{root_name}\\{base_path}\\{key_name}"
                        self._delete_key_recursively(base_key_handle, key_name, full_key_path, cleaned_entries)
            except FileNotFoundError:
                continue # 경로가 없으면 건너뜀
            except Exception as e:
                root_name = HKEY_MAP.get(root_hkey, "Unknown_HKEY")
                logging.error(f"Error while cleaning software keys in {mask_name(root_name)}\\{mask_name(base_path)}: {e}")

    def cleanup_registry_entries(self, program_name: str, publisher: str, install_path: str) -> Dict[str, Any]:
        """프로그램과 관련된 레지스트리 항목들을 안전하게 정리"""
        try:
            cleaned_entries = []
            
            # 1. Uninstall 레지스트리 항목 제거
            uninstall_paths = [
                r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
                r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            ]
            
            for base_path in uninstall_paths:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path) as key:
                        sub_keys_to_remove = []
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            sub_key_name = winreg.EnumKey(key, i)
                            try:
                                with winreg.OpenKey(key, sub_key_name) as sub_key:
                                    try:
                                        name = winreg.QueryValueEx(sub_key, "DisplayName")[0]
                                        if name.lower() == program_name.lower():
                                            sub_keys_to_remove.append(sub_key_name)
                                    except OSError:
                                        continue
                            except OSError:
                                continue
                        
                        # 발견된 항목들 제거
                        for sub_key_name in sub_keys_to_remove:
                            try:
                                winreg.DeleteKey(key, sub_key_name)
                                cleaned_entries.append(f"{base_path}\\{sub_key_name}")
                                logging.info(f"Removed uninstall registry: {mask_name(sub_key_name)}")
                            except OSError as e:
                                logging.warning(f"Failed to remove uninstall registry {mask_name(sub_key_name)}: {e}")
                                
                except FileNotFoundError:
                    continue
            
            # 2. 파일 확장자 연결 제거
            file_assoc_paths = [
                r"Software\Classes",
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"
            ]
            
            for base_path in file_assoc_paths:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path) as key:
                        self._cleanup_file_associations(key, program_name, cleaned_entries)
                except FileNotFoundError:
                    continue
            
            # 3. 시작 프로그램 항목 제거
            startup_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce")
            ]
            for root, startup_path in startup_paths:
                try:
                    with winreg.OpenKey(root, startup_path, 0, winreg.KEY_ALL_ACCESS) as key:
                        values_to_remove = []
                        for i in range(winreg.QueryInfoKey(key)[1]):
                            try:
                                value_name, value_data, _ = winreg.EnumValue(key, i)
                                if install_path and value_data and install_path.lower() in value_data.lower():
                                    values_to_remove.append(value_name)
                            except OSError:
                                continue
                        
                        for value_name in values_to_remove:
                            try:
                                winreg.DeleteValue(key, value_name)
                                cleaned_entries.append(f"{startup_path}\\{value_name}")
                                logging.info(f"Removed startup entry: {mask_name(value_name)}")
                            except OSError as e:
                                logging.warning(f"Failed to remove startup entry {mask_name(value_name)}: {e}")
                except FileNotFoundError:
                    continue

            # 4. Software 키에 남은 프로그램/제작사 관련 키 제거
            if not self.dry_run:
                self._cleanup_software_keys(program_name, publisher, cleaned_entries)
            else:
                logging.info(f"[Dry Run] Skipping general software key cleanup for '{mask_name(program_name)}'")

            logging.info(f"Registry cleanup completed for '{mask_name(program_name)}'. Cleaned {len(cleaned_entries)} entries.")
            return {"status": "success", "message": f"Cleaned {len(cleaned_entries)} registry entries", "cleaned_entries": cleaned_entries}
            
        except Exception as e:
            logging.error(f"Registry cleanup error for '{mask_name(program_name)}': {e}")
            return {"status": "failure", "message": str(e)}

    def _cleanup_file_associations(self, key, program_name: str, cleaned_entries: List[str]):
        """파일 확장자 연결을 정리하는 헬퍼 메서드"""
        try:
            for i in range(winreg.QueryInfoKey(key)[0]):
                sub_key_name = winreg.EnumKey(key, i)
                try:
                    with winreg.OpenKey(key, sub_key_name) as sub_key:
                        # 프로그램 이름이 포함된 확장자 연결 찾기
                        try:
                            default_value = winreg.QueryValue(sub_key, "")
                            if program_name.lower() in default_value.lower():
                                winreg.DeleteKey(key, sub_key_name)
                                cleaned_entries.append(f"File association: {sub_key_name}")
                                logging.info(f"Removed file association: {mask_name(sub_key_name)}")
                        except OSError:
                            continue
                except OSError:
                    continue
        except OSError:
            pass

    def get_uninstall_info(self, program_name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """프로그램 이름으로 UninstallString, 게시자, 설치 경로를 찾아 반환"""
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
                                    try:
                                        install_location = winreg.QueryValueEx(sub_key, "InstallLocation")[0]
                                    except OSError:
                                        install_location = None
                                    
                                    if 'msiexec.exe' in uninstall_string.lower() and '/qn' not in uninstall_string.lower():
                                        uninstall_string = uninstall_string.replace('/I', '/X').replace('/i', '/x') + ' /qn'
                                    return uninstall_string, publisher, install_location
                            except OSError:
                                continue
            except FileNotFoundError:
                continue
        return None, None, None

    def forceful_uninstall_program(self, program_name: str, install_path: str, publisher: str) -> Dict[str, Any]:
        """표준 제거 실패 시 파일 및 레지스트리를 직접 제거하는 강제 제거 로직"""
        logging.warning(f"Start Forceful Uninstall: '{mask_name(program_name)}'")

        # 1. 최종 안전장치
        if publisher and publisher.lower() in self.protected_publishers:
            return {"status": "failure", "message": f"Protected Publisher: '{mask_name(program_name)}'"}
        if install_path and any(os.path.normpath(install_path).lower().startswith(p) for p in self.protected_paths if p):
             return {"status": "failure", "message": f"Protected Path: '{mask_name(program_name)}'"}

        # 2. 관련 프로세스 종료
        if install_path:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    if proc.info['exe'] and os.path.normpath(proc.info['exe']).startswith(os.path.normpath(install_path)):
                        self.terminate_process(proc.info['pid'])
                except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
                    continue
        
        # 3. 설치 폴더 삭제
        path_delete_result = {"status": "success"} # default success
        if install_path:
            path_delete_result = self.delete_path(install_path)
            if path_delete_result['status'] == 'failure':
                return path_delete_result # 삭제 실패 시 여기서 중단 및 결과 반환

        # 4. 레지스트리 정리
        registry_cleanup_result = self.cleanup_registry_entries(program_name, publisher, install_path)
        if path_delete_result['status'] == 'failure' or registry_cleanup_result['status'] == 'failure':
            # 실패 원인을 종합하여 메시지 생성
            fail_msg = path_delete_result.get('message', '') + " " + registry_cleanup_result.get('message', '')
            logging.error(f"Forceful uninstall failed for '{mask_name(program_name)}': {fail_msg.strip()}")
            return {"status": "failure", "message": fail_msg.strip()}

        # 모든 작업이 성공했으면 결과 반환
        clean_count = len(registry_cleanup_result.get('cleaned_entries', []))
        final_message = f"Successfully Forcefully Uninstalled: '{mask_name(program_name)}'"
        if clean_count > 0:
            final_message += f" and cleaned {clean_count} registry entries"
        return {"status": "success", "message": final_message}

    def uninstall_program(self, program_name: str) -> Dict[str, Any]:
        """프로그램 제거를 시도하고, 실패 시 강제 제거를 시도하는 2단계 로직"""
        uninstall_command, publisher, install_path = self.get_uninstall_info(program_name)

        if not uninstall_command:
            logging.warning(f"Uninstall info not found for '{mask_name(program_name)}'. Attempting forceful removal...")
            # 강제 제거에 필요한 최소 정보 (게시자, 설치 경로)라도 찾아야 함
            # 이 정보마저 없다면, 프로그램 이름만으로 강제 제거 시도
            if not publisher or not install_path:
                # SystemProfiler 인스턴스 생성하여 get_installed_programs 호출
                profiler = SystemProfiler()
                all_programs = profiler.get_installed_programs()
                found = next((p for p in all_programs if p['name'].lower() == program_name.lower()), None)
                if found:
                    publisher = found.get('publisher')
                    install_path = found.get('install_location')
        
            # 정보가 하나라도 있으면 강제 제거 진행
            if publisher or install_path:
                return self.forceful_uninstall_program(program_name, install_path, publisher)
            else:
                 return {"status": "failure", "message": f"Cannot find any info to forcefully uninstall '{mask_name(program_name)}'"}
                
        if publisher and publisher.lower() in self.protected_publishers:
            return {"status": "failure", "message": f"Protected Publisher: '{mask_name(program_name)}'"}
        
        # 1단계: 표준 제거 시도
        try:
            logging.info(f"Standard Uninstall Attempt: '{mask_name(program_name)}'")
            subprocess.run(uninstall_command, check=True, shell=True, capture_output=True, text=True, startupinfo=subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW), timeout=60)
            
            # 제거 후에도 프로그램 정보가 남아있는지 확인하여 실제 성공 여부 판단
            # 잠시 대기 후 레지스트리 재확인
            time.sleep(2) 
            check_command, _, _ = self.get_uninstall_info(program_name)
            if check_command:
                 logging.warning(f"Standard uninstall reported success, but '{mask_name(program_name)}' is still found. Proceeding to forceful removal.")
                 return self.forceful_uninstall_program(program_name, install_path, publisher)
            
            return {"status": "success", "message": f"Successfully Uninstalled: '{mask_name(program_name)}'"}

        except subprocess.CalledProcessError as e:
            logging.warning(f"Standard Uninstall Failed for '{mask_name(program_name)}' with exit code {e.returncode}.")
            return self.forceful_uninstall_program(program_name, install_path, publisher)
        except subprocess.TimeoutExpired:
            logging.warning(f"Standard Uninstall Timeout for '{mask_name(program_name)}'.")
            return self.forceful_uninstall_program(program_name, install_path, publisher)
        except Exception as e:
            # 일반적인 예외에서는 e를 직접 출력하지 않아 경로 노출 방지
            logging.warning(f"Standard Uninstall Failed for '{mask_name(program_name)}' with an unexpected error.")
            return self.forceful_uninstall_program(program_name, install_path, publisher)

    async def execute_cleanup(self, cleanup_list: List[Dict]) -> List[Dict]:
        final_results = []
        for item in cleanup_list:
            if item.get('command_type') == 'uninstall_program':
                result_details = await asyncio.to_thread(self.uninstall_program, item["program_name"])
                final_results.append({
                    "name": item.get("name"),
                    "masked_name": item.get("masked_name"),
                    "path": item.get("path"),
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
        logging.info(f"정찰병 늑대 에이전트가 {HOST}:{PORT}에서 대기 중... 아우--- 🐺🐾")
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("사용자 요청으로 서버를 종료합니다. 잘 가! 🤗")