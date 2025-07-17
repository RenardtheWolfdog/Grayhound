// src/components/Dashboard.tsx
import './Dashboard.scss';

interface DashboardProps {
  setCurrentView: (view: string) => void;
}

export const Dashboard = ({ setCurrentView }: DashboardProps) => {
  return (
    <div className="container dashboard">
      <h2>🐺 Grayhound 🐺</h2>
      <div className="dashboard-cards">
        <div className="card" onClick={() => setCurrentView('scan')}>
          <h3>💻 Scan & Clean PC</h3>
          <p>Find and remove bloatware and potential threats from your system.</p>
        </div>
        <div className="card" onClick={() => setCurrentView('db_update')}>
          <h3>🔄 Update Bloatware DB</h3>
          <p>Keep your definitions up-to-date with the latest information.</p>
        </div>
        <div className="card" onClick={() => setCurrentView('db_view')}>
          <h3>🗄️ View & Ignore DB</h3>
          <p>Manage the list of programs that Grayhound identifies as bloatware.</p>
        </div>
      </div>
    </div>
  );
}; 