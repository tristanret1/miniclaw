import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AgentList } from './pages/AgentList';
import { AgentDetail } from './pages/AgentDetail';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-zinc-950 text-zinc-100">
        <Routes>
          <Route path="/" element={<Navigate to="/agents" replace />} />
          <Route path="/agents" element={<AgentList />} />
          <Route path="/agents/:id" element={<AgentDetail />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
