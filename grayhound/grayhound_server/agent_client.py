# agent_client.py
# Grayhound 서버와 로컬 시스템 에이전트(RaikaOptimizer) 간의 WebSocket 통신 클라이언트

import asyncio
import logging
import json
from typing import Dict, List, Optional
import websockets

class OptimizerAgentClient:
    """RaikaOptimizer 에이전트와 WebSocket으로 통신하는 클라이언트"""

    def __init__(self, host='localhost', port=9001):
        """
        클라이언트 초기화
        Args:
            host (str): 로컬 에이전트의 호스트 주소
            port (int): 로컬 에이전트의 포트 번호
        """
        self.url = f"ws://{host}:{port}"
        self.websocket = None

    async def _connect(self):
        """로컬 에이전트에 WebSocket 연결을 시도"""
        if self.websocket:
            try:
                # 연결 상태 확인을 위해 ping 시도
                pong_waiter = await self.websocket.ping()
                await asyncio.wait_for(pong_waiter, timeout=1.0)
                return True  # 이미 연결된 경우
            except:
                pass  # 연결이 끊어진 경우 새로 연결
        try:
            self.websocket = await websockets.connect(self.url)
            logging.info(f"로컬 에이전트({self.url})에 성공적으로 연결되었습니다.")
            return True
        except Exception as e:
            logging.error(f"로컬 에이전트({self.url})에 연결할 수 없습니다: {e}")
            self.websocket = None
            return False

    async def _send_command(self, command: dict) -> bool:
        """로컬 에이전트에 명령을 전송."""
        if not await self._connect():
            logging.error("에이전트에 연결되지 않아 명령을 보낼 수 없습니다.")
            return False
        if not self.websocket:
            logging.error("WebSocket 연결이 없습니다.")
            return False
        try:
            await self.websocket.send(json.dumps(command))
            logging.info(f"에이전트에 명령 전송: {command.get('command')}")
            return True
        except Exception as e:
            logging.error(f"에이전트에 명령을 보내는 중 오류 발생: {e}")
            return False

    async def _receive_response(self, timeout=180.0) -> Optional[Dict]:
        """로컬 에이전트로부터 응답을 수신."""
        if not self.websocket:
            return None
        try:
            response_str = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
            return json.loads(response_str)
        except asyncio.TimeoutError:
            logging.error(f"{timeout}초 내에 에이전트로부터 응답이 없습니다.")
            return None
        except Exception as e:
            logging.error(f"에이전트로부터 응답을 받는 중 오류 발생: {e}")
            return None

    async def _close(self):
        """연결을 종료."""
        if self.websocket:
            await self.websocket.close()
            logging.info(f"로컬 에이전트({self.url})와의 연결을 종료했습니다.")
            self.websocket = None

    async def _execute_task(self, command: dict, timeout: int) -> Optional[Dict]:
        """연결, 명령 전송, 응답 수신, 연결 종료의 전체 과정을 수행."""
        try:
            if await self._send_command(command):
                return await self._receive_response(timeout=timeout)
        finally:
            await self._close()
        return None

    async def get_system_profile(self) -> Optional[Dict]:
        """에이전트에게 시스템 프로파일링을 명령하고 결과를 반환."""
        logging.info("시스템 프로파일링 요청 시작...")
        response = await self._execute_task({"command": "profile_system"}, timeout=180)
        if response and response.get("type") == "system_profile_data":
            return response.get("data")
        logging.error(f"유효한 프로필 데이터를 받지 못했습니다: {response}")
        return None

    async def execute_cleanup_plan(self, cleanup_list: List[Dict]) -> Optional[List]:
        """에이전트에게 정리 계획을 전달하고 실행 결과를 반환. (Phase A용)"""
        logging.info("시스템 정리 요청 시작...")
        command = {"command": "cleanup", "list": cleanup_list}
        response = await self._execute_task(command, timeout=300)
        if response and response.get("type") == "cleanup_result":
            return response.get("data")
        logging.error(f"유효한 정리 결과를 받지 못했습니다: {response}")
        return None
    
    async def execute_phase_b_cleanup(self, cleanup_list: List[Dict]) -> Optional[List[Dict]]:
        """Phase B: UI 기반 정리 실행"""
        logging.info("Phase B: UI 기반 정리 요청 시작...")
        command = {"command": "phase_b_cleanup", "list": cleanup_list}
        response = await self._execute_task(command, timeout=300)
        if response and response.get("type") == "phase_b_result":
            return response.get("data")
        logging.error(f"유효한 Phase B 결과를 받지 못했습니다: {response}")
        return None

    async def execute_phase_c_cleanup(self, cleanup_list: List[Dict]) -> Optional[List[Dict]]:
        """Phase C: 강제 정리 실행"""
        logging.info("Phase C: 강제 정리 요청 시작...")
        command = {"command": "phase_c_cleanup", "list": cleanup_list}
        response = await self._execute_task(command, timeout=300)
        if response and response.get("type") == "phase_c_result":
            return response.get("data")
        logging.error(f"유효한 Phase C 결과를 받지 못했습니다: {response}")
        return None