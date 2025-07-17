// src/components/DBViewer.tsx
import { useState, useEffect, useRef } from 'react';
import './DBViewer.scss';

interface BloatwareItem {
  id: string;
  name: string;
  reason: string;
  risk_score: number;
  ignored: boolean;
}

interface BackendMessage {
  type: 'db_list' | 'error' | 'progress';
  data: any;
}

interface DBViewerProps {
  setCurrentView: (view: string) => void;
}

export const DBViewer = ({ setCurrentView }: DBViewerProps) => {
  const [dbList, setDbList] = useState<BloatwareItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState("Initializing...");

  const ws = useRef<WebSocket | null>(null);

  // ✅ 백엔드 메시지 처리 로직
  const handleBackendMessage = (payload: string) => {
    try {
      const output: BackendMessage = JSON.parse(payload);
      if (output.type === 'db_list') {
        const formattedData = output.data.map((item: any) => ({
          ...item,
          id: item.program_name,
          name: item.program_name,
          ignored: item.ignored === 'Yes'
        }));
        setDbList(formattedData);
        setStatus(`Total ${formattedData.length} items loaded.`);
        setIsLoading(false);
      } else if (output.type === 'error') {
        setStatus(`Error: ${output.data}`);
        setIsLoading(false);
      } else if (output.type === 'progress') {
        setStatus(output.data.status || output.data);
      }
    } catch (e) {
        setStatus(payload); // JSON 파싱 실패 시 일반 로그로 처리 (예: Python의 print문)
    }
  };

  useEffect(() => {
    ws.current = new WebSocket('ws://localhost:8765');
    
    ws.current.onopen = () => {
      setStatus("Connected to server. Fetching DB list...");
      fetchDbList(); // 연결 성공 시 DB 목록 바로 요청
    };

    ws.current.onmessage = (event) => {
      handleBackendMessage(event.data);
    };

    ws.current.onerror = () => {
      setStatus("Failed to connect to the server.");
      setIsLoading(false);
    };
    
    // 컴포넌트 언마운트 시 연결 종료
    return () => {
      ws.current?.close();
    };
  }, []); // 최초 렌더링 시 한 번만 실행

  const fetchDbList = () => {
    if (ws.current?.readyState !== WebSocket.OPEN) {
      setStatus("Server is not connected.");
      return;
    }
    setIsLoading(true);
    setStatus("Fetching DB list from server...");
    ws.current.send(JSON.stringify({ command: 'view_db' }));
  };

  const handleSaveChanges = () => {
    if (ws.current?.readyState !== WebSocket.OPEN) {
      setStatus("Server is not connected.");
      return;
    }
    setIsLoading(true);
    setStatus("Saving ignore list...");
    const ignoredNames = dbList.filter(item => item.ignored).map(item => item.name);
    
    // WebSocket으로 'save-ignore-list' 명령 전송
    ws.current.send(JSON.stringify({
      command: "save_ignore_list",
      args: [JSON.stringify(ignoredNames)]
    }));
  };

  const handleToggleIgnore = (id: string) => {
    setDbList(dbList.map(item => 
      item.id === id ? { ...item, ignored: !item.ignored } : item
    ));
  };

  return (
    <div className="container db-viewer">
      <h2>🗄️ View & Ignore DB</h2>
      <p>Check the items you want to ignore during a PC scan. Click 'Save Changes' to apply.</p>
      <div className="row">
        <button onClick={handleSaveChanges} disabled={isLoading}>Save Changes</button>
        <button onClick={fetchDbList} disabled={isLoading}>Refresh List</button>
        <button type="button" onClick={() => setCurrentView('dashboard')}>Back to Dashboard</button>
      </div>
      
      {isLoading && <p>{status}</p>}
      
      <table className="styled-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Reason</th>
            <th>Risk</th>
            <th>Ignore</th>
          </tr>
        </thead>
        <tbody>
          {dbList.map(item => (
            <tr key={item.id}>
              <td>{item.name}</td>
              <td>{item.reason}</td>
              <td>{item.risk_score}</td>
              <td>
                <input
                  type="checkbox"
                  checked={item.ignored}
                  onChange={() => handleToggleIgnore(item.id)}
                  id={`ignore-checkbox-${item.id}`}
                  title="Add this item to the ignore list"
                  aria-label={`${item.name} ignore`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};