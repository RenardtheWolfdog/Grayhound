// src/App.tsx
import { useState } from "react";
import { DBUpdater } from "./components/DBUpdater";
import { Dashboard } from "./components/Dashboard";
import { DBViewer } from "./components/DBViewer";
import { SystemScanner } from "./components/SystemScanner";
import "./App.scss";

function App() {
  const [currentView, setCurrentView] = useState("dashboard");
  const [language, setLanguage] = useState("en");

  const renderView = () => {
    switch (currentView) {
      case "db_update":
        return <DBUpdater setCurrentView={setCurrentView} setLanguage={setLanguage} />;
      case "db_view":
        return <DBViewer setCurrentView={setCurrentView} />;
      case "scan":
        return <SystemScanner setCurrentView={setCurrentView} language={language} />;
      case "dashboard":
      default:
        return <Dashboard setCurrentView={setCurrentView} />;
    }
  };

  return (
    <div className="layout">
      {/* <aside className="sidebar">
        <h1>🐺 Grayhound</h1>
        <nav>
          <button onClick={() => setCurrentView("dashboard")}>🏠 Dashboard</button>
          <button onClick={() => setCurrentView("scan")}>💻 Scan & Clean</button>
          <button onClick={() => setCurrentView("db_update")}>🔄 Update DB</button>
          <button onClick={() => setCurrentView("db_view")}>🗄️ View/Ignore DB</button>
        </nav>
      </aside> */}
      <main className="main-content">{renderView()}</main>
    </div>
  );
}

export default App;