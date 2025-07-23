// src/components/DBUpdater.tsx
import React, { useState, useEffect, useRef } from 'react';
import './DBUpdater.scss';

// --- 인터페이스 정의 ---
interface Queries {
  known_bloatware_queries: string[];
  general_search_queries: string[];
}

interface GeneratedQueriesState  {
  original_queries: Queries;
  masked_queries: Queries;
}

interface BackendMessage {
  type: 'progress' | 'error' | 'db_queries_generated' | 'db_list';
  data: any;
}

// 경고 메시지 다국어 지원
const warnings = {
  en: "⚠️ Review the queries. Proceeding will start web crawling and DB updates. This may take several minutes. The creators are not responsible for any problems that may occur.",
  ko: "⚠️ 쿼리를 검토하세요. 계속 진행하면 웹 크롤링 및 DB 업데이트가 시작됩니다. 이 작업은 몇 분 정도 소요될 수 있습니다. 발생할 수 있는 모든 문제에 대해 제작자는 책임지지 않습니다.",
  ja: "⚠️ クエリを確認してください。続行すると、WebクロールとDBの更新が開始されます。これには数分かかる場合があります。発生する可能性のある問題について、作成者は責任を負いません。",
  zh: "⚠️ 请检查查询。继续操作将开始网络爬取和数据库更新。这可能需要几分钟时间。对于可能出现的任何问题，创作者不承担任何责任。",
};

export const DBUpdater = ({ setCurrentView, setLanguage }: { setCurrentView: (view: string) => void, setLanguage: (lang: string) => void }) => {
  const [updateStep, setUpdateStep] = useState('form');
  const [generatedQueries, setGeneratedQueries] = useState<GeneratedQueriesState | null>(null);
  const [progressLog, setProgressLog] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isProcessFinished, setIsProcessFinished] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState('en');
  const logContainerRef = useRef<HTMLDivElement>(null);

  const ws = useRef<WebSocket | null>(null);

  // 컴포넌트가 처음 마운트될 때 기본 언어를 설정
  useEffect(() => {
    handleCountryChange({ target: { value: 'South Korea' } } as React.ChangeEvent<HTMLSelectElement>);
  }, []);

  // ✅ WebSocket 연결 및 메시지 핸들러 설정
  useEffect(() => {
    // WebSocket 서버 주소 (Grayhound_Tauri.py가 실행되는 주소)
    ws.current = new WebSocket('ws://localhost:8765');

    ws.current.onopen = () => {
      setProgressLog(prev => [...prev, '[INFO] 🛡️ Grayhound Server Connected.']);
    };

    ws.current.onmessage = (event) => {
      handleBackendMessage(event.data);
    };

    ws.current.onerror = (error) => {
      setProgressLog(prev => [...prev, `[ERROR] ❌ WebSocket Error: ${JSON.stringify(error)}`]);
      setIsLoading(false);
    };

    ws.current.onclose = () => {
      setProgressLog(prev => [...prev, '[INFO] 🛡️ Server Connection Closed.']);
    };

    // 컴포넌트가 언마운트될 때 WebSocket 연결을 정리
    return () => {
      ws.current?.close();
    };
  }, []); // 컴포넌트 마운트 시 한 번만 실행

  useEffect(() => {
    // 로그가 추가될 때마다 자동으로 맨 아래로 스크롤
    if (logContainerRef.current) {
        logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [progressLog]);

  // ✅ 백엔드 메시지 처리 로직
  const handleBackendMessage = (payload: string) => {
    try {
      const output: BackendMessage = JSON.parse(payload);

      switch (output.type) {
        case 'progress':
          // progress 메시지 처리 - data가 객체인 경우와 문자열인 경우 모두 처리
          let statusMessage = '';
          if (typeof output.data === 'string') {
            statusMessage = output.data;
          } else if (output.data?.status) {
            statusMessage = output.data.status;
          } else if (output.data) {
            statusMessage = JSON.stringify(output.data);
          }
          
          if (statusMessage) {
            setProgressLog(prev => [...prev, `[INFO] ${statusMessage}`]);
          }
          break;
        case 'error':
          // error 메시지 처리
          const errorMessage = typeof output.data === 'string' ? output.data : JSON.stringify(output.data);
          setProgressLog(prev => [...prev, `[ERROR] ❌ ${errorMessage}`]);
          setIsLoading(false);
          setIsProcessFinished(true);
          break;
        case 'db_queries_generated':
          setGeneratedQueries(output.data);
          setUpdateStep('confirm');
          setIsLoading(false);
          setProgressLog(prev => [...prev, '[SUCCESS] ✅ AI-generated queries are ready for review.']);
          break;
        case 'db_list':
          setIsLoading(false);
          setIsProcessFinished(true);
          setProgressLog(prev => [...prev, '[SUCCESS] 🎉 Database update complete!']);
          break;
        default:
            // JSON 형식이지만 type이 정의되지 않은 경우, 일반 로그로 처리
          setProgressLog(prev => [...prev, `[LOG] ${payload}`]);
          break;
      }
    } catch (e) {
      // JSON 파싱에 실패하면 일반 텍스트 로그로 간주하고 출력
      setProgressLog(prev => [...prev, `[LOG] ${payload}`]);
    }
  };

  const handleGenerateQueries = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (ws.current?.readyState !== WebSocket.OPEN) {
      setProgressLog(prev => [...prev, '[ERROR] ❌ WebSocket not connected.']);
      return;
    }
    setIsLoading(true);
    setUpdateStep('updating');
    setProgressLog(['[INFO] ⏳ Requesting AI to generate search queries...']);

    const formData = new FormData(e.currentTarget);
    const country = formData.get("country") as string;
    const os = formData.get("os") as string;

    // WebSocket을 통해 명령 전송
    ws.current?.send(JSON.stringify({
      command: 'update_db',
      args: [country, os]
    }));
  };

  const handleConfirmUpdate = async () => {
    if (!generatedQueries || ws.current?.readyState !== WebSocket.OPEN) return;
    setIsLoading(true);
    setUpdateStep('updating');
    setProgressLog(prev => [...prev, '[INFO] 👍 Queries confirmed. Starting DB update process...']);
 
    // WebSocket을 통해 명령 전송
    ws.current?.send(JSON.stringify({
      command: 'confirm_db_update',
      args: [JSON.stringify(generatedQueries.original_queries)]
    }));
  };

  const handleBackToDashboard = () => {
    // 쿼리가 생성되었으나 아직 업데이트가 완료되지 않을 상태일 시 경고창을 띄움.
    if (generatedQueries && !isProcessFinished) {
      if (window.confirm("Warning: If you go back now, the generated query results will be lost. Are you sure you want to proceed?")) {
        setCurrentView('dashboard');
      }
    } else {
      setCurrentView('dashboard');
    }
  };

  const handleCancelUpdate = () => {
    if (window.confirm("Warning: If you go back now, the generated query results will be lost. Are you sure you want to proceed?")) {
      setUpdateStep('form');
      setProgressLog([]);
    }
  };
  
  // 국가 선택 시 언어 선택 변경
  const handleCountryChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const country = e.target.value;
    let lang = 'en';
    switch (country) {
      case 'South Korea':
        lang = 'ko';
        break;
      case 'USA':
        lang = 'en';
        break;
      case 'China':
        lang = 'zh';
        break;
      case 'India':
        lang = 'en';
        break;
      case 'Japan':
        lang = 'ja';
        break;
    }
    setLanguage(lang);
    setCurrentLanguage(lang);
  };
  
  const renderForm = () => (
    <form onSubmit={handleGenerateQueries}>
      <div className="form-group">
        <label htmlFor="country">Country:</label>
        <select name="country" id="country" defaultValue="South Korea" onChange={handleCountryChange}>
            <option value="South Korea">South Korea</option>
            <option value="USA">United States</option>
            <option value="China">China</option>
            <option value="India">India</option>
            <option value="Japan">Japan</option>
        </select>
      </div>
      <div className="form-group">
        <label htmlFor="os">OS:</label>
        <select name="os" id="os" defaultValue="Windows 11">
            <option value="Windows 11">Windows 11</option>
            <option value="Windows 10">Windows 10</option>
            <option value="macOS Sonoma" disabled>macOS Sonoma (Coming soon)</option>
            <option value="Android" disabled>Android (Coming soon)</option>
        </select>
      </div>
      <div className="row">
        <button type="submit" disabled={isLoading}>Generate Queries</button>
        <button type="button" onClick={() => handleBackToDashboard()}>Back to Dashboard</button>
      </div>
    </form>
  );

  const renderConfirm = () => (
    <div className="confirm-container">
      <h4>AI-Generated Queries</h4>
      <div className="report-box query-box">
        <strong>Known Bloatware (Grayware) Targets:</strong>
        <ul>{generatedQueries?.masked_queries.known_bloatware_queries.map((q, i) => <li key={`k-${i}`}>{q}</li>)}</ul>
        <strong>General Search Queries:</strong>
        <ul>{generatedQueries?.masked_queries.general_search_queries.map((q, i) => <li key={`g-${i}`}>{q}</li>)}</ul>
      </div>
      <p className="warning">{warnings[currentLanguage as keyof typeof warnings] || warnings['en']}</p>
      <div className="row">
        <button onClick={() => handleConfirmUpdate()} disabled={isLoading}>Confirm & Start Update</button>
        <button type="button" onClick={() => handleCancelUpdate()} disabled={isLoading}>Cancel</button>
        <button type="button" onClick={() => handleBackToDashboard()} disabled={isLoading}>Back to Dashboard</button>
      </div>
    </div>
  );
  
  const renderProgress = () => (
    <div className="report-box progress-log" ref={logContainerRef}>
      {progressLog.map((log, i) => <p key={i}>{log}</p>)}
    </div>
  );

  return (
    <div className="container">
      <h2>🕵️ Update Bloatware DB</h2>
      {updateStep === 'form' && !isLoading && renderForm()}
      {updateStep === 'confirm' && !isLoading && renderConfirm()}
      
      {progressLog.length > 0 && 
        <div className="progress-container">
            <h4>Update Progress</h4>
            {renderProgress()}
        </div>
      }
      
      {isLoading && <p className="loading-text">Working... please wait.</p>}
      {isProcessFinished && 
          <div className="row">
              <button type="button" onClick={() => handleBackToDashboard()}>Back to Dashboard</button>
          </div>
      }
    </div>
  );
};