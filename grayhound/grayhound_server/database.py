# database.py
# MongoDB connection and data management for Grayhound

import asyncio
import logging
import configparser
import os
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- MongoDB Atlas 연결 설정 ---
try:
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
    config.read(config_path)
    
    username = config['DEFAULT']['username']
    password = config['DEFAULT']['password']
    dbname = config['DEFAULT']['dbname']
    mongo_url = f'mongodb+srv://{username}:{password}@{dbname}.udmyrmv.mongodb.net/'

    async_client = AsyncIOMotorClient(mongo_url)
    async_db = async_client[dbname]
    threat_collection = async_db.threat_intelligence
    user_pref_collection = async_db.user_preferences
    logging.info("Successfully connected to MongoDB Atlas.")
except Exception as e:
    logging.error(f"Failed to read MongoDB configuration file or connect to MongoDB: {e}")
    async_client = None
    
# --- 보안 에이전트 관련 함수 ---

async def get_threat_count() -> int:
    """threat_intelligence 컬렉션에 있는 모든 항목의 개수를 반환"""
    if not async_client: return 0
    return await threat_collection.count_documents({})

async def async_get_all_threats() -> list:
    """threat_intelligence 컬렉션에 있는 모든 문서를 가져옴"""
    if not async_client: return []
    try:
        threats = []
        cursor = threat_collection.find({}, {'_id': 0})
        async for threat in cursor:
            threats.append(threat)
        return threats
    except Exception as e:
        logging.error(f"Failed to fetch threat intelligence from MongoDB: {e}")
        return []
    
async def async_get_threats_with_ignore_status(user_name: str) -> list:
    """
    DB의 모든 위협 목록을 가져오면서, 각 항목이 특정 사용자의
    무시 목록에 포함되어 있는지 여부('ignored' 필드)를 추가하여 반환.
    """
    if not async_client: return []
    
    # 위협 목록과 무시 목록을 동시에 비동기적으로 조회
    threats_task = async_get_all_threats()
    ignore_list_task = async_get_ignore_list_for_user(user_name)
    all_threats, ignore_list = await asyncio.gather(threats_task, ignore_list_task)
    
    # 빠른 조회를 위해 무시 목록을 Set으로 변환
    ignore_set = {item.lower() for item in ignore_list}
    
    for threat in all_threats:
        # 'program_name'키가 없을 경우를 대비해 .get() 사용
        program_name = threat.get('program_name', '').lower()
        if program_name in ignore_set:
            threat['ignored'] = 'Yes'
        else:
            threat['ignored'] = 'No'
        
    return all_threats
    
async def async_update_threats(threat_data_list: list):
    """
    수집된 위협 데이터 목록을 MongoDB에 업데이트(또는 새로 추가).
    """
    if not async_client or not threat_data_list:
        logging.warning("DB가 연결되지 않았거나 업데이트할 데이터가 없어 건너뜁니다.")
        return

    operations = []
    for item in threat_data_list:
        # 프로그램 이름을 기준으로 데이터를 찾고, 없으면 새로 삽입(upsert=True)합니다.
        filter_query = {'program_name': item['program_name']}
        update_document = {'$set': item}
        operations.append(UpdateOne(filter_query, update_document, upsert=True))

    if not operations:
        return

    try:
        result = await threat_collection.bulk_write(operations)
        logging.info(f"DB 업데이트 완료. 추가: {result.upserted_count}, 수정: {result.modified_count}")
    except Exception as e:
        logging.error(f"DB 업데이트 중 오류 발생: {e}")
    
# --- 사용자별 무시 목록 관리 함수 ---

async def async_add_to_ignore_list(user_name: str, item_name: str):
    """특정 아이템을 사용자의 무시 목록에 추가함."""
    if not all([async_client, user_name, item_name]): return
    await user_pref_collection.update_one(
        {'user_name': user_name},
        {'$addToSet': {'ignore_list': item_name.lower()}},
        upsert=True
    )
    logging.info(f"Added '{item_name}' to {user_name}'s ignore list.")

async def async_remove_from_ignore_list(user_name: str, item_name: str):
    """특정 아이템을 사용자의 무시 목록에서 삭제함."""
    if not all([async_client, user_name, item_name]): return
    await user_pref_collection.update_one(
        {'user_name': user_name},
        {'$pull': {'ignore_list': item_name.lower()}}
    )
    logging.info(f"Removed '{item_name}' from {user_name}'s ignore list.")
    
async def async_get_ignore_list_for_user(user_name: str) -> list[str]:
    """사용자의 무시 목록을 반환."""
    if not all([async_client, user_name]): return []
    preferences = await user_pref_collection.find_one({'user_name': user_name})
    return preferences.get('ignore_list', []) if preferences else []

async def async_save_ignore_list(user_name: str, ignore_list: list[str]):
    """사용자의 전체 무시 목록을 덮어쓰기하여 저장"""
    if not all([async_client, user_name]): return
    
    # 중복 제거 및 소문자 변환
    unique_lower_list = list(set(item.lower() for item in ignore_list))
    
    await user_pref_collection.update_one(
        {'user_name': user_name},
        {'$set': {'ignore_list': unique_lower_list}},
        upsert=True
    )
    logging.info(f"Saved {len(unique_lower_list)} items to {user_name}'s ignore list.")
