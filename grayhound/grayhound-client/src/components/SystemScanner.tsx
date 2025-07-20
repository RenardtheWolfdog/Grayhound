// src/components/SystemScanner.tsx
import { useState, useEffect, useRef } from 'react';
// import { invoke } from '@tauri-apps/api/core'
import './SystemScanner.scss';

interface ScanResult {
  id: string;
  name: string;
  masked_name: string;
  reason: string;
  risk_score: number;
  path: string;
  pid: number | null;
  type: 'program' | 'process';
  clean: boolean; // 클라이언트에서 정리 여부를 관리하기 위한 상태
}

interface CleanupResult {
  name: string;
  masked_name: string;
  guide_masked_name?: string; // 가이드 메시지에 쓰일 마스킹된 이름
  path: string;
  status: 'success' | 'failure';
  message: string;
}

interface BackendMessage {
  type: 'scan_result' | 'progress' | 'cleanup_complete' | 'error';
  data: any;
}

interface SystemScannerProps {
  setCurrentView: (view: string) => void;
  language: string;
}

// 경고 메시지 다국어 지원
const warnings = {
  en: "⚠️ IMPORTANT: This can delete important files! If you remove the wrong program, your system or other programs may not work properly. The creators are not responsible for any problems that may occur. Do you really want to proceed?",
  ko: "⚠️ 중요: 중요한 파일을 삭제할 수 있습니다! 잘못된 프로그램을 제거하면 시스템이나 다른 프로그램이 제대로 작동하지 않을 수 있습니다. 발생할 수 있는 모든 문제에 대해 제작자는 책임지지 않습니다. 정말로 진행하시겠습니까?",
  ja: "⚠️ 重要：これにより重要なファイルが削除される可能性があります！間違ったプログラムを削除すると、システムや他のプログラムが正常に動作しなくなる可能性があります。発生する可能性のある問題について、作成者は責任を負いません。本当に続行しますか？",
  zh: "⚠️ 重要：这可能会删除重要文件！如果删除错误的程序，您的系统或其他程序可能无法正常工作。对于可能出现的任何问题，创作者概不负责。您真的要继续吗？",
};

// ✨ 가이드 텍스트 다국어 지원
const guideTexts = {
  en: "Please go to 'Settings > Apps > Installed apps' to manually uninstall the programs listed below.",
  ko: "'설정 > 앱 > 설치된 앱'으로 이동하여 아래 목록의 프로그램을 직접 제거하세요.",
  ja: "「設定 > アプリ > インストールされているアプリ」に移動し、以下のリストにあるプログラムを手動でアンインストールしてください。",
  zh: "请前往“设置 > 应用 > 安装的应用”，手动卸载下方列出的程序。",
};

// 정규식 특수문자를 이스케이프하는 헬퍼 함수
// const escapeRegExp = (str: string) => {
//   return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
// };

export const SystemScanner = ({ setCurrentView, language }: SystemScannerProps) => {
  const [step, setStep] = useState('idle'); // 'idle', 'scanning', 'results', 'cleaning', 'report', 'error'
  const [scanResults, setScanResults] = useState<ScanResult[]>([]);
  const [progressLog, setProgressLog] = useState<string[]>([]);
  const [finalReport, setFinalReport] = useState("");
  const [cleanupResults, setCleanupResults] = useState<CleanupResult[]>([]);
  const [error, setError] = useState("");
  const [riskThreshold, setRiskThreshold] = useState(6); // 위험도 임계값 상태
  const logContainerRef = useRef<HTMLDivElement>(null);

  const ws = useRef<WebSocket | null>(null);

  // ✅ 백엔드 메시지 처리 로직 통합 핸들러
  const handleBackendMessage = (payload: string) => {
    try {
        const { type, data } = JSON.parse(payload) as BackendMessage;

        switch (type) {
        case 'scan_result':
            if (data && data.length > 0) {
                const initialResults = data.map((item: Omit<ScanResult, 'clean'>) => ({ 
                  ...item, 
                  id: item.name, 
                  masked_name: item.masked_name || item.name,
                  clean: true 
                }));
                setScanResults(initialResults);
                setProgressLog(prev => [...prev, '📊 Scan complete. Review the results below.']);
                setStep('results');
            } else {
                // 위협이 발견되지 않았을 경우
                setFinalReport("🎉 Congratulations! No bloatware found in the system.");
                setStep('report');
            }
            break;
        case 'progress':
            // data가 객체일 경우 status 필드를 사용하고, 아닐 경우 data 자체를 사용
            const status = typeof data === 'object' && data !== null && data.status ? data.status : data;
            setProgressLog(prev => [...prev, `[INFO] ${status}`]);
            break;
        case 'cleanup_complete':
              setFinalReport(data.llm_feedback);
              setCleanupResults(data.results); // 구조화된 결과 저장
              setProgressLog(prev => [...prev, '📋 Cleaning complete. See the final report.']);
              setStep('report');
              break;
        case 'error':
            setError(data);
            setStep('error');
            break;
        }
    } catch (e) {
        // JSON 파싱 실패 시 일반 로그로 처리
        setProgressLog(prev => [...prev, `[LOG] ${payload}`]);
    }
  };

  // ✅ WebSocket 연결 설정
  useEffect(() => {
    ws.current = new WebSocket('ws://localhost:8765');
    ws.current.onopen = () => {
      setProgressLog(["[INFO] Ready to scan."]);
    };
    ws.current.onmessage = (event) => {
      handleBackendMessage(event.data);
    };
    ws.current.onerror = () => {
      setError("Connection to server failed. Please ensure the server is running.");
      setStep('error');
    };
    return () => {
      ws.current?.close();
    };
  }, []);

  useEffect(() => {
    // 로그가 업데이트될 때마다 맨 아래로 스크롤
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [progressLog]);

  const handleScan = () => {
    if (ws.current?.readyState !== WebSocket.OPEN) {
      setError("Server is not connected.");
      setStep('error');
      return;
    }
    setStep('scanning');
    setScanResults([]);
    setProgressLog(['🔍 Starting system scan...']);
    setError("");
    setFinalReport("");
    // scan 요청 시 riskThreshold도 함께 전달
    ws.current.send(JSON.stringify({ command: "scan", args: ["[]", riskThreshold.toString()] }));
  };
  
  const handleClean = () => {
    // 다국어 경고 메시지 표시
    const userConfirmed = window.confirm(warnings[language as keyof typeof warnings] || warnings['en']);
    if (!userConfirmed) {
      return;
    }

    if (ws.current?.readyState !== WebSocket.OPEN) {
      setError("Server is not connected.");
      setStep('error');
      return;
    }
    const itemsToClean = scanResults.filter(item => item.clean);
    if (itemsToClean.length === 0) {
      alert("Please select at least one item to clean.");
      return;
    }
    setStep('cleaning');
    setProgressLog(prev => [...prev, `🧹 Starting to clean ${itemsToClean.length} items...`]);

    // clean 요청 시 language도 함께 전달
    ws.current.send(JSON.stringify({ 
      command: "clean", 
      args: [JSON.stringify(itemsToClean), language] 
    }));
  };

  const handleBackToDashboard = () => {
    // 스캔 결과가 있고, 아직 정리(cleaning)나 리포트 단계가 아닐 때 경고
    if (scanResults.length > 0 && (step === 'results' || step === 'cleaning')) {
       if (window.confirm("Warning: If you go back, the current scan results will be discarded. Are you sure?")) {
        setCurrentView('dashboard');
      }
    } else {
      setCurrentView('dashboard');
    }
  };

  const toggleClean = (id: string) => {
    setScanResults(scanResults.map(item => 
      item.id === id ? { ...item, clean: !item.clean } : item
    ));
  };

  const renderProgress = () => (
    <div className="report-box progress-log" ref={logContainerRef}>
        <h4>Scan Progress</h4>
        {progressLog.map((log, i) => <p key={i}>{log}</p>)}
    </div>
  );

  const renderResults = () => (
    <div className="results-container">
        <h4>Scan Results</h4>
        <div className="results-list">
        {scanResults.map(item => {
                // 경로 마스킹 로직
                // const maskedPath = item.path && item.path !== 'N/A'
                //     ? item.path.replace(new RegExp(escapeRegExp(item.name), 'gi'), item.masked_name)
                //     : item.path;

                return (
                    <div key={item.id} className="result-item">
                        <input type="checkbox" id={`clean-${item.id}`} checked={!!item.clean} onChange={() => toggleClean(item.id)} />
                        <label htmlFor={`clean-${item.id}`}>
                            <strong>{item.masked_name}</strong> (Risk: {item.risk_score})
                            <span className="reason">{item.reason}</span>
                            {/* 마스킹된 경로를 표시 */}
                            {/* <code className="path">{maskedPath}</code> */}
                        </label>
                    </div>
                );
            })}
        </div>
        <div className="row">
            <button onClick={handleClean} disabled={scanResults.filter(i => i.clean).length === 0}>Clean Selected Items</button>
            <button type="button" onClick={handleScan}>Scan Again</button>
            <button type="button" onClick={() => handleBackToDashboard()}>Back to Dashboard</button>
        </div>
    </div>
  );

  const renderReport = () => {
    const trulyFailedItems = cleanupResults.filter(item => item.status === 'failure');

    return (
      <div className="report-box">
          <h3>Final Report</h3>
          <pre>{finalReport}</pre>

          {/*--- 수동 제거 가이드 ---*/}
          {trulyFailedItems.length > 0 && (
            <div className="manual-cleanup-guide">
              <h4>Manual Cleanup Guide</h4>
              {/* 다국어 텍스트 표시 */}
              <p>{guideTexts[language as keyof typeof guideTexts] || guideTexts['en']}</p>
              
              <ul>
                {trulyFailedItems.map(item => (
                  <li key={item.name}>
                    {/* 새로운 마스킹 이름(guide_masked_name) 사용, 없으면 기존 masked_name 사용 */}
                    <span>{item.guide_masked_name || item.masked_name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <button type="button" onClick={handleScan}>Scan Again</button>
          <button type="button" onClick={() => handleBackToDashboard()}>Back to Dashboard</button>
      </div>
    );
  }

  const renderError = () => (
      <div className="error-container">
          <h3>Error</h3>
          <pre className="error-log">{error}</pre>
          <button type="button" onClick={handleScan}>Try Scan Again</button>
          <button type="button" onClick={() => handleBackToDashboard()}>Back to Dashboard</button>
      </div>
  );

  const renderIdle = () => (
    <>
      <div className="risk-info">
        <h4>Risk Score Guide</h4>
        <p><span className="risk-high">7-10:</span> Harmful, recommend immediate deletion.</p>
        <p><span className="risk-medium">4-6:</span> Bloatware, consumes resources.</p>
        <p><span className="risk-low">1-3:</span> Normal program. (Not typically shown)</p>
        <p><span className="risk-safe">0:</span> Essential system component.</p>
      </div>
      <div className="risk-slider-container">
        <label htmlFor="risk-slider">Minimum Risk Score to Scan: {riskThreshold}</label>
        <input 
          type="range"
          id="risk-slider"
          min="0"
          max="10"
          value={riskThreshold}
          onChange={(e) => setRiskThreshold(Number(e.target.value))}
          className="risk-slider"
        />
      </div>
      <button onClick={handleScan} className="start-button">Start PC Scan</button>
      <button type="button" onClick={() => handleBackToDashboard()}>Back to Dashboard</button>
    </>
  );

  return (
    <div className="container system-scanner">
      <h2>💻 Scan & Clean PC</h2>
      {step === 'idle' && renderIdle()}
      {(step === 'scanning' || step === 'cleaning') && renderProgress()}
      {step === 'results' && renderResults()}
      {step === 'report' && renderReport()}
      {step === 'error' && renderError()}
    </div>
  );
};