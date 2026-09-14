import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client.js';

export default function App() {
  const [dashboard, setDashboard] = useState(null);
  const [users, setUsers] = useState([]);
  const [notice, setNotice] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setError('');
      const [dashboardData, userData] = await Promise.all([api.getDashboard(), api.getUsers()]);
      setDashboard(dashboardData);
      setUsers(userData);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggleStatus = async (user) => {
    try {
      await api.updateUserStatus(user.id, user.status === 'active' ? 'banned' : 'active');
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  const submitNotice = async (event) => {
    event.preventDefault();
    if (!notice.trim()) return;
    try {
      const result = await api.sendNotice(notice.trim());
      setMessage(`공지 전송 완료 (수신 ${result.delivered}명)`);
      setNotice('');
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="container">
      <header className="header">
        <h1>Backoffice</h1>
        <button onClick={load}>새로고침</button>
      </header>

      {error && <p className="error">{error}</p>}

      <section className="cards">
        <div className="card">
          <span className="label">app-server</span>
          <strong>{dashboard?.appServer.status ?? '-'}</strong>
        </div>
        <div className="card">
          <span className="label">WebSocket 접속자</span>
          <strong>{dashboard?.appServer.wsClients ?? '-'}</strong>
        </div>
        <div className="card">
          <span className="label">전체 사용자</span>
          <strong>{dashboard?.users.total ?? '-'}</strong>
        </div>
        <div className="card">
          <span className="label">정지된 사용자</span>
          <strong>{dashboard?.users.banned ?? '-'}</strong>
        </div>
      </section>

      <section className="panel">
        <h2>실시간 공지</h2>
        <form onSubmit={submitNotice} className="notice-form">
          <input
            value={notice}
            onChange={(e) => setNotice(e.target.value)}
            placeholder="접속 중인 모든 클라이언트에게 보낼 메시지"
          />
          <button type="submit">전송</button>
        </form>
        {message && <p className="success">{message}</p>}
      </section>

      <section className="panel">
        <h2>사용자</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Username</th>
              <th>Email</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.id}</td>
                <td>{user.username}</td>
                <td>{user.email}</td>
                <td>
                  <span className={`badge ${user.status}`}>{user.status}</span>
                </td>
                <td>
                  <button onClick={() => toggleStatus(user)}>
                    {user.status === 'active' ? '정지' : '해제'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
